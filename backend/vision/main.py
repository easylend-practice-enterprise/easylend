import http.client
import ipaddress
import logging
import os
import secrets
import shutil
import socket
import time
from contextlib import asynccontextmanager
from io import BytesIO
from urllib.parse import urlparse

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from pydantic import BaseModel
from ultralytics import YOLO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model variable
model: YOLO | None = None


def _env_flag(name: str) -> bool:
    """Interpret common truthy env-var values."""
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def is_safe_url(url: str) -> bool:
    """Resolve all DNS targets and reject non-global destinations to reduce SSRF risk."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False

    try:
        addr_info = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or 443,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror:
        return False

    for info in addr_info:
        ip_text = info[4][0]
        ip_obj = ipaddress.ip_address(ip_text)
        if not ip_obj.is_global:
            return False

    return True


# Lifespan event manager
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load or export the YOLO model in OpenVINO format."""
    global model

    if _env_flag("SKIP_MODEL_LOADING"):
        logger.info("Skipping model loading/export due to SKIP_MODEL_LOADING flag")
        model = None
        yield
        logger.info("Shutting down...")
        return

    model_path = os.getenv("MODEL_PATH", "models/best.pt")
    openvino_dir = model_path.replace(".pt", "_openvino_model")

    try:
        # Check if model files exist; it's normal for fresh installations to have neither
        if not os.path.exists(model_path) and not os.path.exists(openvino_dir):
            logger.warning(
                f"No model found at {model_path}. Service starting in degraded mode. "
                "Call /update-model endpoint to download a model."
            )
            model = None
        else:
            if not os.path.exists(openvino_dir):
                logger.info(
                    "Exporting model to OpenVINO format for CPU acceleration..."
                )
                temp_model = YOLO(model_path)
                temp_model.export(format="openvino")

            logger.info("Loading OpenVINO optimized model...")
            model = YOLO(openvino_dir)
            logger.info("Model loaded successfully")
    except Exception:
        logger.exception("Failed to load model")
        model = None

    yield

    logger.info("Shutting down...")


# Initialize FastAPI app
app = FastAPI(
    title="EasyLend Vision API",
    description="AI Vision Service for object detection",
    version="1.0.0",
    lifespan=lifespan,
)

# Security setup
security = HTTPBearer()


# Pydantic schemas
class Detection(BaseModel):
    class_name: str
    confidence: float


class PredictionResponse(BaseModel):
    status: str
    count: int
    detections: list[Detection]


class ModelUpdateRequest(BaseModel):
    download_url: str


# Security dependency
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify the Bearer token provided in the Authorization header."""
    expected_token = os.getenv("VISION_API_KEY")
    if not expected_token:
        logger.error("VISION_API_KEY environment variable is not set")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error",
        )

    if not secrets.compare_digest(credentials.credentials, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token",
        )

    return credentials.credentials


def restart_server():
    """Wait 2 seconds and restart the server."""
    time.sleep(2)
    os._exit(0)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if model is not None else "unhealthy",
        "model_loaded": model is not None,
    }


# Prediction endpoint
@app.post("/predict", response_model=PredictionResponse, tags=["Predictions"])
def predict(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),  # noqa: ARG001
) -> PredictionResponse:
    """Run object detection on the provided image."""
    # Validate content type is an image (check before model availability)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not available",
        )

    try:
        image_data = file.file.read()
        image = Image.open(BytesIO(image_data))

        logger.info(f"Running prediction on image: {file.filename}")
        results = model.predict(source=image, imgsz=640)

        detections: list[Detection] = []
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    class_name = result.names.get(class_id, f"class_{class_id}")
                    detections.append(
                        Detection(class_name=class_name, confidence=confidence)
                    )

        logger.info(f"Detected {len(detections)} objects")
        return PredictionResponse(
            status="success",
            count=len(detections),
            detections=detections,
        )

    except Exception:
        logger.exception("Error during prediction")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error processing image",
        )


@app.post("/update-model", tags=["Management"])
def update_model(
    payload: ModelUpdateRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_token),
):
    """Update the AI model from a secure HTTPS URL."""
    if not is_safe_url(payload.download_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsafe model URL.",
        )

    parsed_url = urlparse(payload.download_url)
    hostname = parsed_url.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsafe model URL.",
        )

    port = parsed_url.port or 443
    path_with_query = parsed_url.path or "/"
    if parsed_url.query:
        path_with_query = f"{path_with_query}?{parsed_url.query}"

    logger.info(f"Downloading new model from: {hostname}")
    model_path = os.getenv("MODEL_PATH", "models/best.pt")
    backup_path = f"{model_path}.backup"
    openvino_dir = model_path.replace(".pt", "_openvino_model")

    try:
        if os.path.exists(model_path):
            logger.info("Creating backup of the current model...")
            shutil.copy2(model_path, backup_path)

        conn = http.client.HTTPSConnection(hostname, port=port, timeout=60)
        try:
            conn.request(
                "GET",
                path_with_query,
                headers={"User-Agent": "EasyLend-Vision-Bot"},
            )
            response = conn.getresponse()

            # Strict checks on download response
            if response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Model download failed with status {response.status}",
                )

            content_type = response.getheader("Content-Type") or ""
            if content_type.startswith("text/html"):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model download failed: Received HTML instead of model file",
                )

            with open(model_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)

            # Verify the file is not empty
            if os.path.getsize(model_path) == 0:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model download failed: File is empty",
                )
        finally:
            conn.close()

        if os.path.exists(openvino_dir):
            shutil.rmtree(openvino_dir)

        logger.info("New model downloaded. Scheduled restart in 2 seconds...")
        background_tasks.add_task(restart_server)

        return {"detail": "Model updated. Service will restart in 2 seconds."}

    except HTTPException:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, model_path)
        raise
    except Exception:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, model_path)

        logger.exception("Error updating model. Backup restored.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update failed, backup restored",
        )

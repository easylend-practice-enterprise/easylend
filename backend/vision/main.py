import http.client
import logging
import os
import shutil
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


# Lifespan event manager
@asynccontextmanager
async def lifespan(_app: FastAPI):  # <-- underscore toegevoegd
    """Load or export the YOLO model in OpenVINO format."""
    global model

    MODEL_PATH = os.getenv("MODEL_PATH", "models/best.pt")
    OPENVINO_DIR = MODEL_PATH.replace(".pt", "_openvino_model")

    try:
        if not os.path.exists(OPENVINO_DIR):
            logger.info("Exporting model to OpenVINO format for CPU acceleration...")
            temp_model = YOLO(MODEL_PATH)
            temp_model.export(format="openvino")

        logger.info("Loading OpenVINO optimized model...")
        model = YOLO(OPENVINO_DIR)
        logger.info("Model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        model = None

    yield

    # Cleanup (if any)
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
    """Verify the X-Vision-Token header"""
    expected_token = os.getenv("VISION_API_KEY", "insecure-vision-secret-123!")

    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API token"
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
    file: UploadFile = File(...), token: str = Depends(verify_token)
) -> PredictionResponse:
    """
    Run object detection on the provided image.

    Args:
        file: Image file to analyze
        token: API token (Authorization: Bearer <token> header)

    Returns:
        PredictionResponse with detected objects
    """
    # Check if model is loaded
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not available",
        )

    try:
        # Read and parse the image
        image_data = file.file.read()
        image = Image.open(BytesIO(image_data))

        # Run prediction
        logger.info(f"Running prediction on image: {file.filename}")
        results = model.predict(source=image, imgsz=640)

        # Extract detections
        detections = []
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
            status="success", count=len(detections), detections=detections
        )

    except Exception as e:
        logger.error(f"Error during prediction: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error processing image: {str(e)}",
        )


@app.post("/update-model", tags=["Management"])
def update_model(
    payload: ModelUpdateRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_token),
):
    """Update the AI model from a secure HTTPS URL."""
    # 1. Security: accept only valid HTTPS URLs
    parsed_url = urlparse(payload.download_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only HTTPS URLs are allowed to prevent SSRF.",
        )

    if parsed_url.hostname in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:  # noqa: S104
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="References to internal or loopback IP addresses are not allowed.",
        )

    logger.info(f"Downloading new model from: {payload.download_url}")
    MODEL_PATH = os.getenv("MODEL_PATH", "models/best.pt")
    BACKUP_PATH = f"{MODEL_PATH}.backup"
    OPENVINO_DIR = MODEL_PATH.replace(".pt", "_openvino_model")

    try:
        # 2. Rollback system: create a backup of the current working model
        if os.path.exists(MODEL_PATH):
            logger.info("Creating backup of the current model...")
            shutil.copy2(MODEL_PATH, BACKUP_PATH)

        # 3. Download het nieuwe model
        path_with_query = parsed_url.path or "/"
        if parsed_url.query:
            path_with_query = f"{path_with_query}?{parsed_url.query}"

        conn = http.client.HTTPSConnection(parsed_url.netloc, timeout=60)
        try:
            conn.request(
                "GET", path_with_query, headers={"User-Agent": "EasyLend-Vision-Bot"}
            )
            response = conn.getresponse()
            if response.status >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Model download failed with status {response.status}",
                )

            with open(MODEL_PATH, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
        finally:
            conn.close()

        # 4. Remove the old optimized version so it will be recompiled
        if os.path.exists(OPENVINO_DIR):
            shutil.rmtree(OPENVINO_DIR)

        logger.info("New model downloaded. Scheduled restart in 2 seconds...")

        # 5. Schedule the restart as a background task and return a tidy response
        background_tasks.add_task(restart_server)

        return {"detail": "Model updated. Service will restart in 2 seconds."}

    except HTTPException:
        if os.path.exists(BACKUP_PATH):
            shutil.copy2(BACKUP_PATH, MODEL_PATH)
        raise
    except Exception as e:
        # Restore backup if the download fails
        if os.path.exists(BACKUP_PATH):
            shutil.copy2(BACKUP_PATH, MODEL_PATH)

        logger.error(f"Error updating model. Backup restored. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed, backup restored: {e}",
        )

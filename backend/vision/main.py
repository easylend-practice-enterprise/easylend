import http.client
import ipaddress
import logging
import os
import secrets
import shutil
import socket
import ssl
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
    description="AI Vision Service for object detection and segmentation",
    version="1.0.0",
    lifespan=lifespan,
)

# Security setup
security = HTTPBearer()


# Pydantic schemas aligned with Main API expectations
class Detection(BaseModel):
    class_name: str
    confidence: float


class DetectResponse(BaseModel):
    status: str
    count: int
    detections: list[Detection]
    locker_empty: bool


class SegmentResponse(BaseModel):
    status: str
    has_damage_detected: bool


class ModelUpdateRequest(BaseModel):
    object_detection_url: str | None = None
    segmentation_url: str | None = None


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


def _validate_image(file: UploadFile) -> bytes:
    """Shared helper to validate and read the uploaded image."""
    allowed = {"image/jpeg", "image/png", "image/webp"}
    max_size = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))

    if not file.content_type or file.content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a JPEG/PNG/WebP image",
        )

    image_data = file.file.read(max_size + 1)
    if len(image_data) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large (max {max_size} bytes)",
        )
    return image_data


@app.post("/detect", response_model=DetectResponse, tags=["Predictions"])
def detect(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),  # noqa: ARG001
) -> DetectResponse:
    """Run object detection on the provided image."""
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not available",
        )

    try:
        image_data = _validate_image(file)

        Image.MAX_IMAGE_PIXELS = int(os.getenv("PIL_MAX_PIXELS", 100_000_000))
        image = Image.open(BytesIO(image_data))
        width, height = image.size
        if width * height > int(os.getenv("MAX_IMAGE_PIXELS", 50_000_000)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image has too many pixels",
            )

        logger.info(f"Running detection on image: {file.filename}")
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

        count = len(detections)
        logger.info(f"Detected {count} objects")

        return DetectResponse(
            status="success",
            count=count,
            detections=detections,
            locker_empty=(count == 0),
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error during detection")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error processing image",
        )


@app.post("/segment", response_model=SegmentResponse, tags=["Predictions"])
def segment(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),  # noqa: ARG001
) -> SegmentResponse:
    """Run segmentation (damage detection) on the provided image."""
    try:
        _validate_image(file)
        logger.info(f"Running segmentation on image: {file.filename}")

        # TODO: Placeholder for actual segmentation logic
        has_damage = False

        return SegmentResponse(
            status="success",
            has_damage_detected=has_damage,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error during segmentation")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error processing image",
        )


def _download_via_ip(
    hostname: str,
    ip: str,
    port: int,
    path_with_query: str,
    headers: dict,
    timeout: int = 60,
) -> http.client.HTTPResponse:
    """Download an HTTPS resource by connecting to a resolved IP while preserving SNI/Host."""
    sock = socket.create_connection((ip, port), timeout=timeout)
    ctx = ssl.create_default_context()
    ssock = ctx.wrap_socket(sock, server_hostname=hostname)

    request_lines = [f"GET {path_with_query} HTTP/1.1", f"Host: {hostname}"]
    for k, v in headers.items():
        request_lines.append(f"{k}: {v}")
    request_lines.append("Connection: close")
    request_lines.append("")
    request_lines.append("")
    req = "\r\n".join(request_lines)
    ssock.sendall(req.encode("utf-8"))

    resp = http.client.HTTPResponse(ssock)
    resp.begin()
    return resp


@app.post("/update-model", tags=["Management"])
def update_model(
    payload: ModelUpdateRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_token),
):
    """Update the AI model from a secure HTTPS URL."""
    target_url = payload.object_detection_url or payload.segmentation_url

    if not target_url or not is_safe_url(target_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsafe model URL.",
        )

    parsed_url = urlparse(target_url)
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

        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        chosen_ip = None
        for info in addr_info:
            candidate = info[4][0]
            ip_obj = ipaddress.ip_address(candidate)
            if not ip_obj.is_global:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or unsafe model URL.",
                )
            if chosen_ip is None or ip_obj.version == 4:
                chosen_ip = candidate

        if not chosen_ip:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to resolve model host",
            )
        chosen_ip = str(chosen_ip)

        temp_path = f"{model_path}.tmp"
        resp = _download_via_ip(
            hostname,
            chosen_ip,
            port,
            path_with_query,
            headers={"User-Agent": "EasyLend-Vision-Bot"},
            timeout=60,
        )

        try:
            if resp.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Model download failed with status {resp.status}",
                )

            content_type = resp.getheader("Content-Type") or ""
            if content_type.startswith("text/html"):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model download failed: Received HTML",
                )

            total = 0
            with open(temp_path, "wb") as out_file:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    total += len(chunk)

            if total == 0:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Model download failed: File is empty",
                )

            os.replace(temp_path, model_path)
        finally:
            try:
                resp.close()
            except Exception:
                logger.exception("Error closing HTTP response socket")

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

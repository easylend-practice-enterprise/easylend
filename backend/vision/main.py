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
from pydantic import BaseModel, ConfigDict
from ultralytics import YOLO  # pyright: ignore[reportPrivateImportUsage]

from config import Settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()

# Global model variables
det_model: YOLO | None = None
seg_model: YOLO | None = None


def is_safe_url(url: str) -> bool:
    """Resolve all DNS targets and reject non-global destinations to reduce SSRF risk."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False

    try:
        addr_info = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or settings.https_default_port,
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


def _load_model(model_path: str, model_type: str) -> YOLO | None:
    """Helper function to load a YOLO model and export to OpenVINO if needed."""
    if not model_path:
        return None
    openvino_dir = model_path.replace(
        settings.model_file_extension, settings.openvino_export_suffix
    )

    try:
        if not os.path.exists(model_path) and not os.path.exists(openvino_dir):
            logger.warning(
                f"No {model_type} model found at {model_path}. Service starting in degraded mode. "
                "Call /update-model endpoint to download a model."
            )
            return None

        if not os.path.exists(openvino_dir):
            logger.info(
                f"Exporting {model_type} model to OpenVINO format for CPU acceleration..."
            )
            temp_model = YOLO(model_path)
            temp_model.export(format="openvino")

        logger.info(f"Loading OpenVINO optimized {model_type} model...")
        logger.info(f"Initializing YOLO26 {model_type} model wrapper...")
        model = YOLO(openvino_dir)
        logger.info(f"YOLO26 {model_type} model loaded successfully")
        return model
    except Exception:
        logger.exception(f"Failed to load {model_type} model")
        return None


# Lifespan event manager
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load or export the YOLO models in OpenVINO format."""
    global det_model, seg_model

    if settings.skip_model_loading:
        logger.info("Skipping model loading/export due to SKIP_MODEL_LOADING flag")
        det_model = None
        seg_model = None
        yield
        logger.info("Shutting down...")
        return

    det_model = _load_model(settings.detection_model_path, "Detection")
    seg_model = _load_model(settings.segmentation_model_path, "Segmentation")

    yield

    logger.info("Shutting down...")


# Initialize FastAPI app
app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan,
)

# Security setup
security = HTTPBearer()


# Pydantic schemas aligned with Main API expectations
class Detection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    class_name: str
    confidence: float


class DetectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    count: int
    detections: list[Detection]
    locker_empty: bool


class SegmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    has_damage_detected: bool


class ModelUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_detection_url: str | None = None
    segmentation_url: str | None = None


# Security dependency
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify the Bearer token provided in the Authorization header."""
    expected_token = settings.vision_api_key
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
    """Wait before restarting the server."""
    time.sleep(settings.restart_delay_seconds)
    os._exit(0)


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy"
        if (det_model is not None and seg_model is not None)
        else "degraded",
        "det_model_loaded": det_model is not None,
        "seg_model_loaded": seg_model is not None,
    }


def _validate_image(file: UploadFile) -> bytes:
    """Shared helper to validate and read the uploaded image."""
    allowed = set(settings.allowed_image_content_types)
    max_size = settings.max_upload_size

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
    # Validate first so invalid files get 400 instead of 503 when degraded
    image_data = _validate_image(file)

    if det_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Detection model is not available",
        )

    image: Image.Image | None = None
    results = None
    try:
        Image.MAX_IMAGE_PIXELS = settings.pil_max_pixels
        image = Image.open(BytesIO(image_data))
        width, height = image.size
        if width * height > settings.max_image_pixels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image has too many pixels",
            )

        logger.info(f"Running detection on image: {file.filename}")
        results = det_model.predict(
            source=image, imgsz=settings.model_inference_image_size
        )

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
    finally:
        if image is not None:
            image.close()
        # Explicitly delete large tensors to avoid memory leaks
        # on exception paths where logger.exception holds strong refs
        results = None
        image = None
        image_data = None

        import gc

        gc.collect()


@app.post("/segment", response_model=SegmentResponse, tags=["Predictions"])
def segment(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),  # noqa: ARG001
) -> SegmentResponse:
    """Run segmentation (damage detection) on the provided image."""
    image_data = _validate_image(file)

    if seg_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Segmentation model is not available",
        )

    image: Image.Image | None = None
    results = None
    try:
        Image.MAX_IMAGE_PIXELS = settings.pil_max_pixels
        image = Image.open(BytesIO(image_data))
        width, height = image.size
        if width * height > settings.max_image_pixels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image has too many pixels",
            )

        logger.info(f"Running segmentation on image: {file.filename}")
        results = seg_model.predict(
            source=image, imgsz=settings.model_inference_image_size
        )

        has_damage = False
        if results and len(results) > 0:
            result = results[0]
            masks = getattr(result, "masks", None)
            if masks is not None and len(masks) > 0:  # type: ignore
                has_damage = True

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
    finally:
        if image is not None:
            image.close()
        # Explicitly delete large tensors to avoid memory leaks
        # on exception paths where logger.exception holds strong refs
        results = None
        image = None
        image_data = None

        import gc

        gc.collect()


def _download_via_ip(
    hostname: str,
    ip: str,
    port: int,
    path_with_query: str,
    headers: dict,
    timeout: int = settings.model_download_timeout_seconds,
) -> http.client.HTTPResponse:
    """Download an HTTPS resource by connecting to a resolved IP while preserving SNI/Host."""
    sock = None
    ssock = None
    try:
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
    finally:
        if ssock is not None:
            ssock.close()
        elif sock is not None:
            sock.close()


def _model_size_error_detail() -> str:
    max_mb = settings.max_model_download_size_bytes // (1024 * 1024)
    return f"Model download exceeds maximum allowed size of {max_mb}MB."


def _update_single_model(url: str, model_path: str):
    """Helper function to download, backup, and update a single model file."""
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsafe model URL.",
        )
    port = parsed_url.port or settings.https_default_port
    path_with_query = parsed_url.path or "/"
    if parsed_url.query:
        path_with_query = f"{path_with_query}?{parsed_url.query}"

    logger.info(f"Downloading new model from: {hostname}")
    backup_path = f"{model_path}{settings.backup_suffix}"
    openvino_dir = model_path.replace(
        settings.model_file_extension, settings.openvino_export_suffix
    )

    # Resolve once — no TOCTOU window. Skip non-global IPs; prefer IPv4.
    addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    chosen_ip: str | None = None
    for info in addr_info:
        candidate = str(info[4][0])
        ip_obj = ipaddress.ip_address(candidate)
        if not ip_obj.is_global:
            continue
        if chosen_ip is None or ip_obj.version == 4:
            chosen_ip = candidate
        if ip_obj.version == 4:
            break

    if not chosen_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No global IP address found for model host.",
        )
    chosen_ip = str(chosen_ip)

    temp_path = f"{model_path}{settings.temp_suffix}"
    try:
        try:
            if os.path.exists(model_path):
                logger.info(f"Creating backup of the current model at {model_path}...")
                shutil.copy2(model_path, backup_path)
        except OSError:
            pass  # No backup needed if model_path doesn't exist yet

        resp = _download_via_ip(
            hostname,
            chosen_ip,
            port,
            path_with_query,
            headers={"User-Agent": settings.model_download_user_agent},
            timeout=settings.model_download_timeout_seconds,
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

            content_length_header = resp.getheader("Content-Length")
            if content_length_header:
                try:
                    content_length = int(content_length_header)
                except ValueError:
                    content_length = None
                if (
                    content_length is not None
                    and content_length > settings.max_model_download_size_bytes
                ):
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=_model_size_error_detail(),
                    )

            total = 0
            with open(temp_path, "wb") as out_file:
                while True:
                    chunk = resp.read(settings.model_download_chunk_size_bytes)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > settings.max_model_download_size_bytes:
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=_model_size_error_detail(),
                        )
                    out_file.write(chunk)

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
    except HTTPException:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, model_path)
        raise
    except Exception as e:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, model_path)
        logger.exception("Error updating model. Backup restored.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update failed, backup restored",
        ) from e
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.post("/update-model", tags=["Management"])
def update_model(
    payload: ModelUpdateRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_token),
):
    """Update the AI models from secure HTTPS URLs."""
    if payload.object_detection_url is None and payload.segmentation_url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide at least one model URL to update.",
        )

    if payload.object_detection_url is not None:
        try:
            _update_single_model(
                payload.object_detection_url, settings.detection_model_path
            )
        except HTTPException as exc:
            raise exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Detection model update failed.",
            ) from exc

    if payload.segmentation_url is not None:
        _update_single_model(payload.segmentation_url, settings.segmentation_model_path)

    logger.info(
        "New model(s) downloaded. Scheduled restart in %s seconds...",
        settings.restart_delay_seconds,
    )
    background_tasks.add_task(restart_server)

    return {
        "message": (
            "Model update received successfully. Service will restart in "
            f"{settings.restart_delay_seconds} seconds."
        )
    }

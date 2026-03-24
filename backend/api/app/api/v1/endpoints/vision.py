import logging
import uuid
from pathlib import Path, PurePath

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.deps import verify_vision_box_token
from app.core.config import settings
from app.schemas.vision import VisionAnalyzeResponse

router = APIRouter(prefix="/vision", tags=["vision"])
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB limit
UPLOAD_DIR = Path("uploads")


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_image(
    _: None = Depends(verify_vision_box_token),
    file: UploadFile = File(...),
) -> VisionAnalyzeResponse:
    # 1. Valideer content type VOORDAT we in het geheugen inlezen
    if not (file.content_type or "").startswith("image/"):
        logger.warning(
            "Rejected non-image upload in vision analyze endpoint.",
            extra={
                "upload_content_type": file.content_type,
                "upload_name": file.filename,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be an image.",
        )

    # 2a. Lees in met een harde limiet (memory protection)
    image_data = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(image_data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large (max {MAX_UPLOAD_SIZE} bytes)",
        )

    # 2b. Genereer een veilige bestandsnaam en sla lokaal op (Copilot Fix)
    safe_filename = PurePath(file.filename).name if file.filename else ""
    file_ext = safe_filename.split(".")[-1] if "." in safe_filename else "jpg"

    # Enforce strict alphanumeric extension to prevent traversal injections
    if not file_ext.isalnum():
        file_ext = "jpg"

    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"

    file_path = UPLOAD_DIR / unique_filename

    # Async disk write to prevent event loop blocking
    async with aiofiles.open(file_path, "wb") as buffer:
        await buffer.write(image_data)

    photo_url = f"/api/v1/images/{unique_filename}"

    # 3. Request naar de AI Microservice (VM2) met de juiste VISION_API_KEY
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.VISION_SERVICE_URL.rstrip('/')}/predict",
                headers={"Authorization": f"Bearer {settings.VISION_API_KEY}"},
                files={
                    "file": (
                        file.filename or "upload",
                        image_data,
                        file.content_type,
                    )
                },
            )
    except httpx.RequestError as exc:
        logger.error(
            "Vision AI request failed.",
            extra={"error": str(exc), "vision_url": settings.VISION_SERVICE_URL},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vision AI service is unavailable.",
        ) from exc

    if response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ):
        logger.error(
            "Vision AI authentication/configuration mismatch.",
            extra={"upstream_status": response.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vision AI authentication is misconfigured.",
        )

    if response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        logger.warning(
            "Vision AI service is temporarily unavailable.",
            extra={"upstream_status": response.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vision AI service is temporarily unavailable.",
        )

    if response.status_code == status.HTTP_400_BAD_REQUEST:
        logger.warning(
            "Vision AI rejected uploaded image as invalid/unsupported.",
            extra={"upstream_status": response.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image is invalid or unsupported.",
        )

    if response.status_code != status.HTTP_200_OK:
        logger.error(
            "Vision AI returned unexpected non-200 response.",
            extra={"upstream_status": response.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI service returned an unexpected response.",
        )

    try:
        payload = response.json()
        payload["photo_url"] = photo_url
        validated_data = VisionAnalyzeResponse(**payload)
    except (ValueError, ValidationError) as exc:
        logger.error("Vision AI returned invalid JSON or unexpected schema.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI service returned invalid data format.",
        ) from exc

    return validated_data

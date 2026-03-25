import logging
import uuid

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.deps import verify_vision_box_token
from app.core.config import settings
from app.core.uploads import UPLOAD_DIR
from app.schemas.vision import VisionAnalyzeResponse

router = APIRouter(prefix="/vision", tags=["vision"])
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB limit


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_image(
    _: None = Depends(verify_vision_box_token),
    file: UploadFile = File(...),
) -> VisionAnalyzeResponse:
    # 1. Validate content type BEFORE reading into memory
    content_type = file.content_type or ""
    allowed_content_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    if content_type not in allowed_content_types:
        logger.warning(
            "Rejected non-image upload in vision analyze endpoint.",
            extra={
                "upload_content_type": content_type,
                "upload_name": file.filename,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a JPEG/PNG/WebP image.",
        )

    # 2a. Read with a hard limit (memory protection)
    image_data = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(image_data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large (max {MAX_UPLOAD_SIZE} bytes)",
        )

    # 2b. Determine file extension from the declared content type (`UploadFile.content_type`).
    # If stronger guarantees are required, inspect the file bytes to validate the actual image format
    # before choosing an extension (e.g., to reject mismatched HEIC/WEBP uploads).
    content_type_ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    file_ext = content_type_ext_map[content_type]
    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"

    file_path = UPLOAD_DIR / unique_filename
    photo_url = f"/api/v1/images/{unique_filename}"

    # 3. Request to the AI Microservice (VM2)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.VISION_SERVICE_URL.rstrip('/')}/predict",
                headers={"Authorization": f"Bearer {settings.VISION_API_KEY}"},
                files={
                    "file": (
                        file.filename or "upload",
                        image_data,
                        content_type,
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
        if not isinstance(payload, dict):
            raise TypeError("Expected dict payload from Vision AI service.")

        payload["photo_url"] = photo_url
        validated_data = VisionAnalyzeResponse(**payload)
    except (TypeError, ValueError, ValidationError) as exc:
        logger.error("Vision AI returned invalid JSON or unexpected schema.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI service returned invalid data format.",
        ) from exc

    # 4. Save to disk ONLY after successful validation (prevents orphan files)
    try:
        async with aiofiles.open(file_path, "wb") as buffer:
            await buffer.write(image_data)
    except OSError as exc:
        logger.error(
            "Failed to save uploaded image to disk.",
            extra={"error": str(exc), "file_path": str(file_path)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable.",
        ) from exc

    return validated_data

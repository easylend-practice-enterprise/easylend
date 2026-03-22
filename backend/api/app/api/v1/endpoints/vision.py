import logging
import uuid
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.api.deps import verify_vision_box_token
from app.core.config import settings
from app.schemas.vision import VisionAnalyzeResponse

router = APIRouter(prefix="/vision", tags=["vision"])
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB limit
UPLOAD_DIR = Path(settings.UPLOAD_DIR)


@router.post("/analyze")
async def analyze_image(
    _: Annotated[None, Depends(verify_vision_box_token)],
    file: Annotated[UploadFile, File()],
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

    # 2b. Genereer een veilige bestandsnaam and map extension from content_type
    content_type = (file.content_type or "").lower()
    ext_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/gif": "gif",
        "image/tiff": "tiff",
    }
    file_ext = ext_map.get(content_type, "jpg")
    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
    file_path = UPLOAD_DIR / unique_filename

    photo_url = f"/api/v1/images/{unique_filename}"

    # Persist uploads only when enabled
    if not getattr(settings, "UPLOADS_ENABLED", True):
        file_path = None
    else:
        try:
            # Use a thread to perform blocking IO so we don't block the event loop
            await run_in_threadpool(file_path.write_bytes, image_data)
        except Exception as exc:
            logger.exception("Failed to write uploaded image to disk")
            # best-effort cleanup
            from contextlib import suppress

            with suppress(Exception):
                if file_path and file_path.exists():
                    file_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist uploaded image",
            ) from exc

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
        # attach photo_url only when persisted
        if file_path is not None:
            payload["photo_url"] = photo_url
        validated_data = VisionAnalyzeResponse(**payload)
    except (ValueError, ValidationError) as exc:
        logger.error("Vision AI returned invalid JSON or unexpected schema.")
        # Cleanup persisted file on validation error
        from contextlib import suppress

        with suppress(Exception):
            if file_path is not None and file_path.exists():
                file_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI service returned invalid data format.",
        ) from exc

    return validated_data

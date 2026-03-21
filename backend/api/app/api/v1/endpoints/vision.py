import logging

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import verify_vision_box_token
from app.core.config import settings
from app.schemas.vision import VisionAnalyzeResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_image(
    _: None = Depends(verify_vision_box_token),
    file: UploadFile = File(...),
) -> VisionAnalyzeResponse:
    image_data = await file.read()

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

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.VISION_SERVICE_URL.rstrip('/')}/predict",
                headers={"Authorization": f"Bearer {settings.VISION_BOX_API_KEY}"},
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
            "Vision AI reported startup/unavailable state.",
            extra={"upstream_status": response.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vision AI service is starting up.",
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
    except ValueError as exc:
        logger.error("Vision AI returned invalid JSON.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI service returned invalid JSON.",
        ) from exc

    logger.info(
        "Vision analyze request proxied successfully.",
        extra={"upload_name": file.filename, "upstream_status": response.status_code},
    )

    return payload

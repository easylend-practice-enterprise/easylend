import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_vision_box_token
from app.core.audit import log_audit_event
from app.core.config import settings
from app.core.uploads import UPLOAD_DIR
from app.core.websockets import manager
from app.db.database import get_db
from app.db.models import (
    Asset,
    AssetStatus,
    EvaluationType,
    Loan,
    LoanStatus,
    Locker,
    LockerStatus,
)
from app.schemas.vision import VisionAnalyzeResponse

router = APIRouter(prefix="/vision", tags=["vision"])
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB limit


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_image(
    _: None = Depends(verify_vision_box_token),
    db: AsyncSession = Depends(get_db),
    loan_id: UUID = Form(...),
    evaluation_type: EvaluationType = Form(...),
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

    # 4. Apply transaction outcome to domain state (BEFORE writing file)
    loan_result = await db.execute(select(Loan).where(Loan.loan_id == loan_id))
    loan = loan_result.scalar_one_or_none()
    if loan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan not found.",
        )

    asset_result = await db.execute(
        select(Asset).where(Asset.asset_id == loan.asset_id)
    )
    asset = asset_result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )

    # 4b. Validate state machine BEFORE querying locker (prevents 404 before 409)
    if evaluation_type == EvaluationType.CHECKOUT:
        if loan.loan_status != LoanStatus.RESERVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Loan must be in RESERVED status for checkout evaluation, not {loan.loan_status}.",
            )
    else:  # EvaluationType.RETURN
        if loan.loan_status != LoanStatus.RETURNING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Loan must be in RETURNING status for return evaluation, not {loan.loan_status}.",
            )
        if loan.return_locker_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Return locker must be assigned before evaluation.",
            )

    locker_id_for_eval = (
        loan.checkout_locker_id
        if evaluation_type == EvaluationType.CHECKOUT
        else loan.return_locker_id
    )
    locker_result = await db.execute(
        select(Locker).where(Locker.locker_id == locker_id_for_eval)
    )
    locker = locker_result.scalar_one_or_none()
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Locker not found.",
        )

    detections = validated_data.detections or []
    has_any_detection = validated_data.count > 0 and len(detections) > 0
    has_damage = any(
        "damage" in detection.class_name.lower() for detection in detections
    )

    led_color = "green"
    outcome = "SUCCESS"

    if evaluation_type == EvaluationType.CHECKOUT:
        if has_any_detection:
            loan.loan_status = LoanStatus.FRAUD_SUSPECTED
            asset.asset_status = AssetStatus.AVAILABLE
            locker.locker_status = LockerStatus.AVAILABLE
            led_color = "red"
            outcome = "FRAUD_SUSPECTED"
        else:
            loan.loan_status = LoanStatus.ACTIVE
            loan.borrowed_at = datetime.now(UTC)
            led_color = "green"
            outcome = "ACTIVE"
    else:  # EvaluationType.RETURN
        if has_damage:
            loan.loan_status = LoanStatus.PENDING_INSPECTION
            asset.asset_status = AssetStatus.PENDING_INSPECTION
            asset.locker_id = locker.locker_id
            locker.locker_status = LockerStatus.MAINTENANCE
            led_color = "red"
            outcome = "PENDING_INSPECTION"
        else:
            loan.loan_status = LoanStatus.COMPLETED
            loan.returned_at = datetime.now(UTC)
            asset.asset_status = AssetStatus.AVAILABLE
            asset.locker_id = locker.locker_id
            locker.locker_status = LockerStatus.OCCUPIED
            led_color = "green"
            outcome = "COMPLETED"

    # 5. Save to disk ONLY after successful validation and state mutations
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

    try:
        await manager.send_command(
            str(locker.kiosk_id),
            {
                "action": "set_led",
                "locker_id": str(getattr(locker, "logical_number", locker.locker_id)),
                "color": led_color,
            },
        )

        await log_audit_event(
            db,
            action_type="VISION_EVALUATION_PROCESSED",
            payload={
                "loan_id": str(loan.loan_id),
                "asset_id": str(asset.asset_id),
                "locker_id": str(locker.locker_id),
                "evaluation_type": evaluation_type.value,
                "outcome": outcome,
                "photo_url": validated_data.photo_url,
            },
        )

        await db.commit()
    except Exception as exc:
        Path(file_path).unlink(missing_ok=True)
        logger.exception("Failed while finalizing vision evaluation transaction.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize vision evaluation.",
        ) from exc

    return validated_data

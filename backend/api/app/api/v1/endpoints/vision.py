import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import verify_vision_box_token
from app.core.audit import log_audit_event
from app.core.config import settings
from app.core.uploads import UPLOAD_DIR
from app.core.websockets import manager
from app.db.database import get_db
from app.db.models import (
    AIEvaluation,
    Asset,
    AssetStatus,
    EvaluationType,
    Loan,
    LoanStatus,
    Locker,
    LockerStatus,
)
from app.schemas.vision import (
    ModelUpdateRequest,
    ModelUpdateResponse,
    VisionAnalyzeResponse,
)

router = APIRouter(prefix="/vision", tags=["vision"])
webhook_router = APIRouter(tags=["vision"])
logger = logging.getLogger(__name__)


def _is_lock_not_available_error(exc: OperationalError) -> bool:
    """
    Best-effort detection of a lock-not-available error coming from the DB.
    We inspect the wrapped DBAPI error (exc.orig) for a lock-specific
    SQLSTATE such as PostgreSQL's 55P03 ("lock_not_available").
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    # PostgreSQL via psycopg/asyncpg exposes SQLSTATE here
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if pgcode == "55P03":
        return True

    # Fallback for SQLite in tests
    message = str(orig).lower()
    return "database is locked" in message or "lock not available" in message


MAX_UPLOAD_SIZE = 10 * 1024 * 1024


class VisionAIServiceError(Exception):
    """Raised to represent a non-200 or otherwise problematic response from the Vision AI upstream."""

    def __init__(self, status_code: int, detail: str):
        if status_code is None:
            raise ValueError("status_code is required")
        if detail is None:
            detail = ""

        try:
            self.status_code = int(status_code)
        except Exception:
            raise ValueError("status_code must be an int")

        # Collapse whitespace and truncate to limit exposure of upstream content
        sanitized = re.sub(r"\s+", " ", str(detail)).strip()
        self.detail = sanitized[:1000]

        super().__init__(
            f"VisionAIServiceError(status_code={self.status_code}, detail={self.detail})"
        )


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_image(
    _: None = Depends(verify_vision_box_token),
    db: AsyncSession = Depends(get_db),
    loan_id: UUID = Form(...),
    evaluation_type: EvaluationType = Form(...),
    file: UploadFile = File(...),
) -> VisionAnalyzeResponse:
    content_type = file.content_type or ""
    allowed_content_types = {"image/jpeg", "image/png", "image/webp"}

    if content_type not in allowed_content_types:
        logger.warning(f"Rejected non-image upload: {file.filename} ({content_type})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a JPEG/PNG/WebP image.",
        )

    image_data = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(image_data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large (max {MAX_UPLOAD_SIZE} bytes)",
        )

    content_type_ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    file_ext = content_type_ext_map[content_type]
    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"

    file_path = UPLOAD_DIR / unique_filename
    photo_url = f"/api/v1/images/{unique_filename}"

    try:
        loan_result = await db.execute(
            select(Loan).where(Loan.loan_id == loan_id).with_for_update(nowait=True)
        )
        loan = loan_result.scalar_one_or_none()
    except OperationalError as exc:
        await db.rollback()
        if not _is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vision evaluation is already processing for this loan. Please try again or wait.",
        )
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found."
        )

    try:
        asset_result = await db.execute(
            select(Asset)
            .where(Asset.asset_id == loan.asset_id)
            .with_for_update(nowait=True)
        )
        asset = asset_result.scalar_one_or_none()
    except OperationalError as exc:
        await db.rollback()
        if not _is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vision evaluation is already processing for this loan. Please try again or wait.",
        )
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found."
        )

    if evaluation_type == EvaluationType.CHECKOUT:
        if loan.loan_status != LoanStatus.RESERVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Loan must be in RESERVED status for checkout, not {loan.loan_status}.",
            )
    else:
        if loan.loan_status != LoanStatus.RETURNING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Loan must be in RETURNING status for return, not {loan.loan_status}.",
            )
        if not loan.return_locker_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Return locker must be assigned before evaluation.",
            )

    locker_id_for_eval = (
        loan.checkout_locker_id
        if evaluation_type == EvaluationType.CHECKOUT
        else loan.return_locker_id
    )
    try:
        locker_result = await db.execute(
            select(Locker)
            .where(Locker.locker_id == locker_id_for_eval)
            .with_for_update(nowait=True)
        )
        locker = locker_result.scalar_one_or_none()
    except OperationalError as exc:
        await db.rollback()
        if not _is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A database error occurred.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vision evaluation is already processing for this loan. Please try again or wait.",
        )

    if not locker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found."
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            detect_req = client.post(
                f"{settings.VISION_SERVICE_URL.rstrip('/')}/detect",
                headers={"Authorization": f"Bearer {settings.VISION_API_KEY}"},
                files={"file": (file.filename or "upload", image_data, content_type)},
            )
            segment_req = client.post(
                f"{settings.VISION_SERVICE_URL.rstrip('/')}/segment",
                headers={"Authorization": f"Bearer {settings.VISION_API_KEY}"},
                files={"file": (file.filename or "upload", image_data, content_type)},
            )
            detect_resp, segment_resp = await asyncio.gather(detect_req, segment_req)

        non_200 = []
        for name, resp in (("detect", detect_resp), ("segment", segment_resp)):
            if resp.status_code != 200:
                try:
                    raw_text = resp.text
                except Exception:
                    raw_text = "<unavailable>"

                safe_text = re.sub(r"\s+", " ", str(raw_text)).strip()[:500]

                if 400 <= resp.status_code < 500:
                    logger.warning(
                        "Vision AI '%s' returned %s: %s",
                        name,
                        resp.status_code,
                        safe_text,
                        extra={"vision_response_excerpt": safe_text},
                    )
                else:
                    logger.error(
                        "Vision AI '%s' returned %s: %s",
                        name,
                        resp.status_code,
                        safe_text,
                        extra={"vision_response_excerpt": safe_text},
                    )

                non_200.append((resp.status_code, safe_text, name))

        if non_200:
            codes = [c for (c, t, n) in non_200]
            if any(c in (401, 403) for c in codes):
                rep = next(c for c in codes if c in (401, 403))
            elif 503 in codes:
                rep = 503
            elif 400 in codes:
                rep = 400
            else:
                rep = codes[0]

            combined_text = " | ".join(f"{name}:{text}" for (c, text, name) in non_200)
            raise VisionAIServiceError(status_code=rep, detail=combined_text)

        detect_payload = detect_resp.json()
        segment_payload = segment_resp.json()

        if not isinstance(detect_payload, dict) or not isinstance(
            segment_payload, dict
        ):
            raise ValueError("Expected dict payload from Vision AI service.")

        locker_empty = detect_payload.get("locker_empty")
        has_damage = segment_payload.get("has_damage_detected")

        if not isinstance(locker_empty, bool) or not isinstance(has_damage, bool):
            raise ValueError("Malformed AI response: missing or non-boolean flags")

        validated_data = VisionAnalyzeResponse(
            status="success",
            count=detect_payload.get("count", 0),
            detections=detect_payload.get("detections", []),
            photo_url=photo_url,
        )

    except (
        httpx.RequestError,
        VisionAIServiceError,
        ValueError,
        TypeError,
        ValidationError,
    ) as exc:
        logger.error(
            f"Vision AI evaluation failed: {str(exc)}",
            extra={"vision_url": settings.VISION_SERVICE_URL},
        )

        if evaluation_type in (EvaluationType.CHECKOUT, EvaluationType.RETURN):
            try:
                loan.loan_status = LoanStatus.PENDING_INSPECTION
                asset.asset_status = AssetStatus.PENDING_INSPECTION
                locker.locker_status = LockerStatus.MAINTENANCE
                asset.locker_id = locker.locker_id

                command_ok = await manager.send_command(
                    str(locker.kiosk_id),
                    {
                        "action": "set_led",
                        "locker_id": str(
                            getattr(locker, "logical_number", locker.locker_id)
                        ),
                        "color": "orange",
                    },
                )
                if not command_ok:
                    logger.warning(
                        "Failed to set LED color to orange for locker_id=%s",
                        locker_id_for_eval,
                    )

                try:
                    error_summary = str(exc)[:200].replace("\n", " ")
                    await log_audit_event(
                        db,
                        action_type="VISION_EVALUATION_FAILED",
                        payload={
                            "evaluation_type": evaluation_type.value,
                            "loan_id": str(loan.loan_id),
                            "asset_id": str(asset.asset_id),
                            "locker_id": str(locker.locker_id),
                            "error_summary": error_summary,
                        },
                    )
                except Exception:
                    logger.exception(
                        "Failed to write audit log for Vision AI failure fallback."
                    )

                await db.commit()
            except Exception as fallback_exc:
                await db.rollback()
                logger.exception(
                    "Failed to persist fallback state after Vision AI failure."
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to persist fallback state.",
                ) from fallback_exc

        if isinstance(exc, httpx.RequestError):
            final_status = status.HTTP_503_SERVICE_UNAVAILABLE
            final_detail = "Vision AI service is unavailable."
        elif isinstance(exc, VisionAIServiceError):
            upstream = getattr(exc, "status_code", None)
            if upstream in (401, 403):
                final_status = status.HTTP_500_INTERNAL_SERVER_ERROR
                final_detail = "Vision AI authentication is misconfigured."
            elif upstream == 503:
                final_status = status.HTTP_503_SERVICE_UNAVAILABLE
                final_detail = "Vision AI service is temporarily unavailable."
            elif upstream == 400:
                final_status = status.HTTP_400_BAD_REQUEST
                final_detail = "Uploaded image is invalid or unsupported."
            else:
                final_status = status.HTTP_502_BAD_GATEWAY
                final_detail = "Vision AI service returned an unexpected response."
        elif isinstance(exc, (TypeError, ValidationError, ValueError)):
            final_status = status.HTTP_502_BAD_GATEWAY
            final_detail = "Vision AI service returned invalid data format."
        else:
            final_status = status.HTTP_503_SERVICE_UNAVAILABLE
            final_detail = "Vision AI service is unavailable."

        raise HTTPException(status_code=final_status, detail=final_detail) from exc

    if evaluation_type == EvaluationType.CHECKOUT:
        if not locker_empty:
            loan.loan_status = LoanStatus.FRAUD_SUSPECTED
            asset.locker_id = locker.locker_id
            asset.asset_status = AssetStatus.AVAILABLE
            locker.locker_status = LockerStatus.OCCUPIED
            led_color = "red"
        else:
            loan.loan_status = LoanStatus.ACTIVE
            loan.borrowed_at = datetime.now(UTC)
            asset.locker_id = None
            locker.locker_status = LockerStatus.AVAILABLE
            led_color = "green"
    else:
        if locker_empty or has_damage:
            loan.loan_status = LoanStatus.PENDING_INSPECTION
            asset.asset_status = AssetStatus.PENDING_INSPECTION
            asset.locker_id = locker.locker_id
            locker.locker_status = LockerStatus.MAINTENANCE
            led_color = "orange"
        else:
            loan.loan_status = LoanStatus.COMPLETED
            loan.returned_at = datetime.now(UTC)
            asset.asset_status = AssetStatus.AVAILABLE
            asset.locker_id = locker.locker_id
            locker.locker_status = LockerStatus.OCCUPIED
            led_color = "green"

    try:
        async with aiofiles.open(file_path, "wb") as buffer:
            await buffer.write(image_data)
    except OSError as exc:
        logger.error(f"Failed to save image to disk: {str(file_path)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable.",
        ) from exc

    try:
        command_ok = await manager.send_command(
            str(locker.kiosk_id),
            {
                "action": "set_led",
                "locker_id": str(getattr(locker, "logical_number", locker.locker_id)),
                "color": led_color,
            },
        )
        if not command_ok:
            logger.warning(
                "Failed to set LED color to %s for locker_id=%s",
                led_color,
                locker_id_for_eval,
            )

        await log_audit_event(
            db,
            action_type="VISION_EVALUATION_PROCESSED",
            payload={
                "loan_id": str(loan.loan_id),
                "asset_id": str(asset.asset_id),
                "locker_id": str(locker.locker_id),
                "evaluation_type": evaluation_type.value,
                "has_damage_detected": has_damage,
                "photo_url": validated_data.photo_url,
            },
        )

        db.add(
            AIEvaluation(
                loan_id=loan.loan_id,
                evaluation_type=evaluation_type,
                photo_url=validated_data.photo_url,
                ai_confidence=validated_data.detections[0].confidence
                if validated_data.detections
                else 0.0,
                has_damage_detected=has_damage,
                model_version="yolo26-dual-model",
                detected_objects={
                    "locker_empty": locker_empty,
                    "detections": [d.model_dump() for d in validated_data.detections]
                    if validated_data.detections
                    else [],
                },
            )
        )
        await db.commit()
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            logger.exception(
                "Failed to rollback DB during finalization error handling."
            )

        Path(file_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize vision evaluation.",
        ) from exc

    return validated_data


@webhook_router.post("/update-model", response_model=ModelUpdateResponse)
async def update_model(
    payload: ModelUpdateRequest,
    _: None = Depends(verify_vision_box_token),
) -> ModelUpdateResponse:
    safe_detect_url = (
        payload.object_detection_url.split("?")[0]
        if payload.object_detection_url
        else ""
    )
    safe_segment_url = (
        payload.segmentation_url.split("?")[0] if payload.segmentation_url else ""
    )

    logger.info(
        "Model update webhook received.",
        extra={
            "object_detection_url_sanitized": safe_detect_url,
            "segmentation_url_sanitized": safe_segment_url,
        },
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.VISION_SERVICE_URL.rstrip('/')}/update-model",
                json=payload.model_dump(),
                headers={"Authorization": f"Bearer {settings.VISION_API_KEY}"},
            )

        if response.status_code != 200:
            upstream_detail = response.text[:500]
            logger.error(
                "Vision microservice returned %s for model-update: %s",
                response.status_code,
                upstream_detail,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Vision microservice returned {response.status_code}: {upstream_detail}",
            )
    except httpx.RequestError as exc:
        logger.error(
            "Failed to forward model-update to Vision microservice: %s",
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with Vision microservice.",
        ) from exc

    return ModelUpdateResponse(message="Model update received successfully.")

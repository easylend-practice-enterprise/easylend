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

from app.api.deps import verify_vision_box_token
from app.core.audit import log_audit_event
from app.core.config import settings
from app.core.state_machine import InvalidLoanTransitionError, LoanStateMachine
from app.core.uploads import UPLOAD_DIR
from app.core.websockets import manager
from app.db.database import AsyncSessionLocal
from app.db.models import (
    AIEvaluation,
    Asset,
    EvaluationType,
    Loan,
    LoanStatus,
    Locker,
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


def _map_vision_failure_to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.RequestError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vision AI service is unavailable.",
        )

    if isinstance(exc, VisionAIServiceError):
        upstream = getattr(exc, "status_code", None)
        if upstream in (401, 403):
            return HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Vision AI authentication is misconfigured.",
            )
        if upstream == 503:
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vision AI service is temporarily unavailable.",
            )
        if upstream == 400:
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image is invalid or unsupported.",
            )
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vision AI service returned an unexpected response.",
        )

    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Vision AI service returned invalid data format.",
    )


def _apply_loan_transition(
    loan: Loan,
    asset: Asset,
    locker: Locker,
    target_status: LoanStatus,
) -> None:
    transition = LoanStateMachine.transition(loan.loan_status, target_status)
    loan.loan_status = transition.loan_status

    if transition.asset_status is not None:
        asset.asset_status = transition.asset_status

    if transition.locker_status is not None:
        locker.locker_status = transition.locker_status


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_image(
    _: None = Depends(verify_vision_box_token),
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
            detail="Image too large.",
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

    # --- Phase 1: Lightweight pre-flight validation ---
    # Uses a short-lived DB session that is returned to the pool BEFORE the
    # slow AI call. This prevents the 30-second Vision AI roundtrip from
    # holding a connection and starving the pool under concurrent load.
    async with AsyncSessionLocal() as phase1_db:
        loan_result = await phase1_db.execute(
            select(Loan).where(Loan.loan_id == loan_id)
        )
        loan = loan_result.scalar_one_or_none()
        if not loan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found."
            )

        asset_result = await phase1_db.execute(
            select(Asset).where(Asset.asset_id == loan.asset_id)
        )
        asset = asset_result.scalar_one_or_none()
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found."
            )

        if asset.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset is no longer active.",
            )

        if evaluation_type == EvaluationType.CHECKOUT:
            if loan.loan_status != LoanStatus.RESERVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Loan must be in RESERVED status for checkout.",
                )
        else:
            if loan.loan_status != LoanStatus.RETURNING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Loan must be in RETURNING status for return.",
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
        locker_result = await phase1_db.execute(
            select(Locker).where(Locker.locker_id == locker_id_for_eval)
        )
        locker = locker_result.scalar_one_or_none()
        if not locker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found."
            )
    # --- Phase 1 session is now CLOSED. Connection returned to pool. ---

    # --- AI Call: No database connection held ---
    # The Vision AI HTTP calls run completely outside any DB session context.
    # Even if these calls take 30 seconds, the connection pool is unaffected.
    locker_empty: bool | None = None
    has_damage: bool | None = None
    validated_data: VisionAnalyzeResponse | None = None
    vision_failure: Exception | None = None
    mapped_failure_http_exception: HTTPException | None = None
    failure_error_summary = ""

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
        vision_failure = exc
        mapped_failure_http_exception = _map_vision_failure_to_http_exception(exc)
        failure_error_summary = str(exc)[:200].replace("\n", " ")

    # --- Phase 2: Acquire a FRESH session, lock rows, apply mutations ---
    # A new session is created here. Row locks are held only for the ~100ms
    # DB write + WS command — NOT for the 30s AI call that just completed.
    # Locking order: Loan → Asset → Locker (deterministic, matches judge_evaluation).
    async with AsyncSessionLocal() as db:
        try:
            locked_loan_result = await db.execute(
                select(Loan).where(Loan.loan_id == loan_id).with_for_update(nowait=True)
            )
            locked_loan = locked_loan_result.scalar_one_or_none()
            if locked_loan is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found."
                )
            loan = locked_loan
        except OperationalError as exc:
            if not _is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="A database error occurred.",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vision evaluation is already processing for this loan. Please try again.",
            )

        locked_locker_id_for_eval = (
            loan.checkout_locker_id
            if evaluation_type == EvaluationType.CHECKOUT
            else loan.return_locker_id
        )
        if locked_locker_id_for_eval is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Return locker must be assigned before evaluation.",
            )
        locker_id_for_eval = locked_locker_id_for_eval

        try:
            locked_asset_result = await db.execute(
                select(Asset)
                .where(Asset.asset_id == loan.asset_id)
                .with_for_update(nowait=True)
            )
            locked_asset = locked_asset_result.scalar_one_or_none()
            if locked_asset is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found."
                )
            asset = locked_asset
        except OperationalError as exc:
            if not _is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="A database error occurred.",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vision evaluation is already processing for this loan. Please try again.",
            )

        try:
            locked_locker_result = await db.execute(
                select(Locker)
                .where(Locker.locker_id == locker_id_for_eval)
                .with_for_update(nowait=True)
            )
            locked_locker = locked_locker_result.scalar_one_or_none()
            if locked_locker is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Locker not found."
                )
            locker = locked_locker
        except OperationalError as exc:
            if not _is_lock_not_available_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="A database error occurred.",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vision evaluation is already processing for this loan. Please try again.",
            )

        if vision_failure is not None:
            try:
                _apply_loan_transition(
                    loan,
                    asset,
                    locker,
                    LoanStatus.PENDING_INSPECTION,
                )
                asset.locker_id = locker.locker_id

                await log_audit_event(
                    db,
                    action_type="VISION_EVALUATION_FAILED",
                    payload={
                        "evaluation_type": evaluation_type.value,
                        "loan_id": str(loan.loan_id),
                        "asset_id": str(asset.asset_id),
                        "locker_id": str(locker.locker_id),
                        "error_summary": failure_error_summary,
                    },
                )
                await db.commit()

                # Hardware command fires AFTER DB commit so that the forensic
                # trail is durable before any side effects are triggered.
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
            except InvalidLoanTransitionError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc
            except Exception as exc:
                try:
                    await db.rollback()
                except Exception:
                    logger.exception(
                        "Failed to rollback DB during Vision fallback finalization error handling."
                    )

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to finalize vision evaluation.",
                ) from exc

            if mapped_failure_http_exception is None:
                mapped_failure_http_exception = HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Vision AI service returned invalid data format.",
                )
            raise mapped_failure_http_exception from vision_failure

        if locker_empty is None or has_damage is None or validated_data is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Vision evaluation did not produce complete data.",
            )

        try:
            if evaluation_type == EvaluationType.CHECKOUT:
                if not locker_empty:
                    _apply_loan_transition(
                        loan,
                        asset,
                        locker,
                        LoanStatus.FRAUD_SUSPECTED,
                    )
                    asset.locker_id = locker.locker_id
                    led_color = "red"
                    await log_audit_event(
                        db,
                        action_type="LOAN_CHECKOUT_FRAUD",
                        payload={
                            "loan_id": str(loan.loan_id),
                            "asset_id": str(asset.asset_id),
                            "locker_id": str(locker.locker_id),
                        },
                        user_id=loan.user_id,
                    )
                else:
                    _apply_loan_transition(
                        loan,
                        asset,
                        locker,
                        LoanStatus.ACTIVE,
                    )
                    loan.borrowed_at = datetime.now(UTC)
                    asset.locker_id = None
                    led_color = "green"
                    await log_audit_event(
                        db,
                        action_type="LOAN_CHECKOUT_CONFIRMED",
                        payload={
                            "loan_id": str(loan.loan_id),
                            "asset_id": str(asset.asset_id),
                            "locker_id": str(locker.locker_id),
                        },
                        user_id=loan.user_id,
                    )
            else:
                if locker_empty or has_damage:
                    _apply_loan_transition(
                        loan,
                        asset,
                        locker,
                        LoanStatus.PENDING_INSPECTION,
                    )
                    asset.locker_id = locker.locker_id
                    led_color = "orange"
                else:
                    _apply_loan_transition(
                        loan,
                        asset,
                        locker,
                        LoanStatus.COMPLETED,
                    )
                    loan.returned_at = datetime.now(UTC)
                    asset.locker_id = locker.locker_id
                    led_color = "green"
                    await log_audit_event(
                        db,
                        action_type="LOAN_RETURN_CONFIRMED",
                        payload={
                            "loan_id": str(loan.loan_id),
                            "asset_id": str(asset.asset_id),
                            "locker_id": str(locker.locker_id),
                        },
                        user_id=loan.user_id,
                    )
        except InvalidLoanTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

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
                    "locker_id": str(
                        getattr(locker, "logical_number", locker.locker_id)
                    ),
                    "color": led_color,
                },
            )
            if not command_ok:
                logger.error(
                    "Failed to set LED color to %s for locker_id=%s — DB committed but LED incorrect.",
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
                        "detections": [
                            d.model_dump() for d in validated_data.detections
                        ]
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

        # Check hardware sync after DB commit succeeds. Raising here is safe —
        # the except block above did not catch HTTPException (it re-raises a 500).
        if not command_ok:
            logger.error(
                "set_led failed for loan_id=%s, locker_id=%s — DB committed but LED incorrect.",
                loan.loan_id,
                locker.locker_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Evaluation recorded but locker LED update failed. Please contact support.",
            )

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
                detail="Vision microservice returned an error. Please try again or contact support.",
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

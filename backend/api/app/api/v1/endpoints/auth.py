import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import security
from app.core.audit import log_audit_event
from app.core.config import settings
from app.core.db_utils import is_lock_not_available_error
from app.core.rate_limit import check_ip_rate_limit
from app.db.database import get_db
from app.db.models import User, UserStatus
from app.db.redis import (
    revoke_refresh_token,
    store_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Brute-force constants (architecture spec: 5 attempts, 15-minute lockout)
_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15
# Compute the exact TTL in seconds from the days setting
_REFRESH_TOKEN_TTL_SECONDS = int(
    timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()
)


# Request / Response schemas (auth-specific, defined inline)


class NfcLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nfc_tag_id: str = Field(..., min_length=1, max_length=100)


class PinLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nfc_tag_id: str = Field(..., min_length=1, max_length=100)
    pin: str = Field(..., min_length=4, max_length=32)


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., min_length=1, max_length=2048)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105


# Shared helper


async def _get_active_user_by_nfc(
    nfc_tag_id: str,
    db: AsyncSession,
    lock_row: bool = False,
) -> User:
    """
    Fetches a user by nfc_tag_id with the role eagerly loaded.
    Raises a generic HTTPException for all failed login attempts
    (unknown badge, deactivated account, or locked account) without
    leaking details about the exact reason or lockout timing.
    """
    query = (
        select(User)
        .options(selectinload(User.role))
        .where(User.nfc_tag_id == nfc_tag_id)
    )

    if lock_row:
        query = query.with_for_update(nowait=True)

    try:
        result = await db.execute(query)
    except OperationalError as exc:
        if is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account is currently in use. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred.",
        ) from exc
    user = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid NFC badge or account status.",
        )

    if user.locked_until:
        if user.locked_until > datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid NFC badge or account status.",
            )
        else:
            # Lockout has expired, grant a fresh set of attempts.
            # This state is committed by the caller in the normal login flow.
            user.locked_until = None
            user.failed_login_attempts = 0

    return user


async def _create_and_store_refresh_token(user_id) -> str:
    refresh_token = security.create_refresh_token(user_id)
    refresh_payload = security.verify_refresh_token(refresh_token)
    try:
        await store_refresh_token(
            user_id=str(refresh_payload.sub),
            jti=str(refresh_payload.jti),
            expires_in_seconds=_REFRESH_TOKEN_TTL_SECONDS,
        )
    except (TimeoutError, RedisError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable. Please try again later.",
        ) from exc
    return refresh_token


# Endpoints


@router.post("/nfc", status_code=status.HTTP_200_OK)
async def nfc_login(
    request: Request,
    body: NfcLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validate an NFC badge before PIN verification.

    Public endpoint for the kiosk sign-in flow.
    Rate-limited: 500 req/min per IP (Layer 2).
    """
    await check_ip_rate_limit(request)
    await _get_active_user_by_nfc(body.nfc_tag_id, db)
    return {"detail": "NFC badge recognized. Enter PIN."}


@router.post("/pin", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def pin_login(
    request: Request,
    body: PinLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Verify the PIN and issue access and refresh tokens.

    Public endpoint for the kiosk sign-in flow.
    Rate-limited: 500 req/min per IP (Layer 2).
    """
    await check_ip_rate_limit(request)

    # Step 1: Look up the user by NFC tag (no row lock yet).
    user = await _get_active_user_by_nfc(body.nfc_tag_id, db, lock_row=False)

    # Step 2: Lock the user row by user_id to serialize all login attempts
    # against this account, regardless of which NFC tag triggered the request.
    # This prevents race conditions when multiple NFC tags map to the same user.
    try:
        locked_result = await db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.user_id == user.user_id)
            .with_for_update(nowait=True)
        )
    except OperationalError as exc:
        if is_lock_not_available_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account is currently in use. Please try again.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred.",
        ) from exc

    user = locked_result.scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid NFC badge or account status.",
        )
    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is locked. Try again later.",
        )

    if not security.verify_pin(body.pin, user.pin_hash):
        user.failed_login_attempts += 1
        remaining_attempts = max(_MAX_ATTEMPTS - user.failed_login_attempts, 0)

        if user.failed_login_attempts >= _MAX_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
            user.failed_login_attempts = _MAX_ATTEMPTS
            try:
                await log_audit_event(
                    db,
                    action_type="LOGIN_FAILED",
                    payload={
                        "nfc_tag_id": body.nfc_tag_id,
                        "reason": "ACCOUNT_LOCKED",
                        "lockout_until": str(user.locked_until),
                    },
                )
            except Exception:
                await db.rollback()
                raise
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is locked. Try again later.",
            )

        try:
            await log_audit_event(
                db,
                action_type="LOGIN_FAILED",
                payload={
                    "nfc_tag_id": body.nfc_tag_id,
                    "reason": "INVALID_PIN",
                    "remaining_attempts": remaining_attempts,
                },
            )
        except Exception:
            await db.rollback()
            raise
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect PIN. {remaining_attempts} attempts remaining.",
        )

    # Successful login: reset brute-force counters
    user.failed_login_attempts = 0
    user.locked_until = None
    try:
        await log_audit_event(
            db,
            action_type="LOGIN_SUCCESS",
            payload={"nfc_tag_id": body.nfc_tag_id},
            user_id=user.user_id,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()

    access_token = security.create_access_token(
        user_id=user.user_id,
        role=user.role.role_name,
    )
    refresh_token = await _create_and_store_refresh_token(user.user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_access_token(
    request: Request,
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Rotate a valid refresh token and return a new token pair.

    Public endpoint for authenticated kiosk sessions.
    Rate-limited: 500 req/min per IP (Layer 2).
    """
    await check_ip_rate_limit(request)
    # 1. Decode and validate the signature and token type
    try:
        refresh_payload = security.verify_refresh_token(body.refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    # 2. Atomically consume the token (prevents token replay / race conditions)
    try:
        token_consumed = await revoke_refresh_token(
            user_id=str(refresh_payload.sub),
            jti=str(refresh_payload.jti),
        )
    except RedisError as e:
        logger.exception(
            "Failed to revoke refresh token during refresh.",
            extra={
                "user_id": str(refresh_payload.sub),
                "jti": str(refresh_payload.jti),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporary service issue. Please try again later.",
        ) from e

    if not token_consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    # 3. Fetch the user from the database
    result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .where(User.user_id == refresh_payload.sub)
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or (user.locked_until is not None and user.locked_until > datetime.now(UTC))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    # 4. Issue a new token pair
    access_token = security.create_access_token(
        user_id=user.user_id,
        role=user.role.role_name,
    )
    refresh_token = await _create_and_store_refresh_token(user.user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(body: RefreshTokenRequest) -> dict:
    """
    Revoke the provided refresh token and end the active session.

    Public endpoint and idempotent by design.
    """
    try:
        payload = security.verify_refresh_token(body.refresh_token)
    except ValueError:
        # Idempotent logout: expired or invalid tokens still return a successful response.
        return {"detail": "Successfully logged out."}

    try:
        await revoke_refresh_token(user_id=str(payload.sub), jti=str(payload.jti))
    except RedisError as e:
        logger.exception(
            "Failed to revoke refresh token during logout.",
            extra={
                "user_id": str(payload.sub),
                "jti": str(payload.jti),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporary service issue. Please try again later.",
        ) from e

    return {"detail": "Successfully logged out."}

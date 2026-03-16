from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import security
from app.core.config import settings
from app.db.database import get_db
from app.db.models import User
from app.db.redis import (
    revoke_refresh_token,
    store_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Brute-force constanten (architecture spec: 5 pogingen, 15 min lockout)
_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15
# Bereken exact het aantal seconden op basis van de dagen in de settings
_REFRESH_TOKEN_TTL_SECONDS = int(
    timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()
)


# Request / Response schemas (auth-specifiek, inline)


class NfcLoginRequest(BaseModel):
    nfc_tag_id: str


class PinLoginRequest(BaseModel):
    nfc_tag_id: str
    pin: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105


# Gedeelde helper


async def _get_active_user_by_nfc(
    nfc_tag_id: str, db: AsyncSession, lock_row: bool = False
) -> User:
    """
    Haalt de user op via nfc_tag_id inclusief eager-loaded role.
    Gooit een generieke HTTPException voor alle mislukte login-pogingen
    (onbekende badge, gedeactiveerd account of geblokkeerd account) zonder
    details over de exacte reden of lockout-timing te lekken.
    """
    query = (
        select(User)
        .options(selectinload(User.role))
        .where(User.nfc_tag_id == nfc_tag_id)
    )

    if lock_row:
        query = query.with_for_update()

    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or (user.locked_until is not None and user.locked_until > datetime.now(UTC))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ongeldige NFC badge of accountstatus.",
        )

    return user


async def _create_and_store_refresh_token(user_id) -> str:
    refresh_token = security.create_refresh_token(user_id)
    refresh_payload = security.verify_refresh_token(refresh_token)
    await store_refresh_token(
        user_id=str(refresh_payload.sub),
        jti=str(refresh_payload.jti),
        expires_in_seconds=_REFRESH_TOKEN_TTL_SECONDS,
    )
    return refresh_token


# Endpoints


@router.post("/nfc", status_code=status.HTTP_200_OK)
async def nfc_login(
    body: NfcLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Stap 1 van de login flow: valideer NFC-badge.

    Controleert of de badge gekend, het account actief en ontgrendeld is.
    Geeft 200 terug zodat de Kiosk App het PIN-scherm kan tonen.
    Alle gebruikers hebben een PIN (pin_hash is NOT NULL in de DB), dus er
    is geen directe NFC-only login.
    """
    await _get_active_user_by_nfc(body.nfc_tag_id, db)
    return {"detail": "NFC badge herkend. Voer PIN in."}


@router.post("/pin", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def pin_login(
    body: PinLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Stap 2 van de login flow: verifieer PIN en geef een JWT access token terug.

    - Blokkeert het account voor _LOCKOUT_MINUTES na _MAX_ATTEMPTS mislukte pogingen.
    - Reset de teller en de lockout bij een succesvolle inlog.
    - TODO (ELP-29): INSERT audit_log LOGIN_SUCCESS / LOGIN_FAILED.
    """
    user = await _get_active_user_by_nfc(body.nfc_tag_id, db, lock_row=True)

    if not security.verify_pin(body.pin, user.pin_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= _MAX_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
            # Reset teller bij het instellen van een lockout zodat na de lockout
            # periode opnieuw _MAX_ATTEMPTS pogingen beschikbaar zijn.
            user.failed_login_attempts = 0
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ongeldige PIN.",
        )

    # Succesvolle inlog: reset brute-force tellers
    user.failed_login_attempts = 0
    user.locked_until = None
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
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # 1. Decode en valideer de signature en type
    try:
        refresh_payload = security.verify_refresh_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    # 2. Atomisch de token consumeren (Voorkomt Token Replay / Race Conditions)
    token_consumed = await revoke_refresh_token(
        user_id=str(refresh_payload.sub),
        jti=str(refresh_payload.jti),
    )

    if not token_consumed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ongeldige refresh token.",
        )

    # 3. Haal de user op uit de DB
    result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .where(User.user_id == refresh_payload.sub)
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or (user.locked_until is not None and user.locked_until > datetime.now(UTC))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ongeldige refresh token.",
        )

    # 4. Maak nieuwe tokens aan
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
    try:
        payload = security.verify_refresh_token(body.refresh_token)
    except ValueError:
        # Idempotent logout: verlopen of ongeldige tokens geven nog steeds succes terug.
        return {"detail": "Succesvol uitgelogd."}

    await revoke_refresh_token(user_id=str(payload.sub), jti=str(payload.jti))
    return {"detail": "Succesvol uitgelogd."}

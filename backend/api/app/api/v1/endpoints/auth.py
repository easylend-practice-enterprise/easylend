from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import security
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Brute-force constanten (architecture spec: 5 pogingen, 15 min lockout) ---
_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


# --- Request / Response schemas (auth-specifiek, inline) ---


class NfcLoginRequest(BaseModel):
    nfc_tag_id: str


class PinLoginRequest(BaseModel):
    nfc_tag_id: str
    pin: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105


# --- Gedeelde helper ---


async def _get_active_user_by_nfc(nfc_tag_id: str, db: AsyncSession) -> User:
    """
    Haalt de user op via nfc_tag_id inclusief eager-loaded role.
    Gooit een generieke HTTPException voor alle mislukte login-pogingen
    (onbekende badge, gedeactiveerd account of geblokkeerd account) zonder
    details over de exacte reden of lockout-timing te lekken.
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .where(User.nfc_tag_id == nfc_tag_id)
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or (
            user.locked_until is not None
            and user.locked_until > datetime.now(UTC)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ongeldige NFC badge of accountstatus.",
        )

    return user


# --- Endpoints ---


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


@router.post("/pin", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK)
async def pin_login(
    body: PinLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    """
    Stap 2 van de login flow: verifieer PIN en geef een JWT access token terug.

    - Blokkeert het account voor _LOCKOUT_MINUTES na _MAX_ATTEMPTS mislukte pogingen.
    - Reset de teller en de lockout bij een succesvolle inlog.
    - TODO (ELP-24): refresh token aanmaken en opslaan in Redis.
    - TODO (ELP-29): INSERT audit_log LOGIN_SUCCESS / LOGIN_FAILED.
    """
    user = await _get_active_user_by_nfc(body.nfc_tag_id, db)

    if not security.verify_pin(body.pin, user.pin_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= _MAX_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
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
    return AccessTokenResponse(access_token=access_token)

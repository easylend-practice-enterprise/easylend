import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import security
from app.core.config import settings
from app.db.database import get_db
from app.db.models import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = security.verify_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.user_id == payload.sub)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not active.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.locked_until is not None and user.locked_until > datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is temporarily locked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role is None or current_user.role.role_name.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions.",
        )
    return current_user


def _verify_device_token(expected_token: str, provided_token: str | None) -> None:
    """Verify a device token with timing-safe comparison and WWW-Authenticate header."""
    if provided_token is None or not secrets.compare_digest(
        provided_token, expected_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token.",
            headers={"WWW-Authenticate": "X-Device-Token"},
        )


async def verify_vision_box_token(
    x_device_token: str | None = Header(None, alias="X-Device-Token"),
) -> None:
    _verify_device_token(settings.VISION_BOX_API_KEY, x_device_token)


async def verify_simulation_token(
    x_device_token: str | None = Header(None, alias="X-Device-Token"),
) -> None:
    _verify_device_token(settings.SIMULATION_API_KEY, x_device_token)

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.token import TokenPayload


def get_secret_hash(secret: str) -> str:
    """Hash a secret string using bcrypt."""
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class RefreshTokenPayload(BaseModel):
    sub: uuid.UUID
    exp: datetime
    jti: uuid.UUID


def _decode_token(token: str, required_claims: list[str]) -> dict:
    claims_to_check = required_claims + ["type"]
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": claims_to_check},
        )
    except ExpiredSignatureError as e:
        raise ValueError("Token has expired.") from e
    except InvalidTokenError as e:
        raise ValueError("Invalid token.") from e


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """
    Creates a signed JWT access token for the specified user.
    Payload contains sub (user_id), role, exp (expiry), jti (unique token ID), and type.
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """
    Creates a signed JWT refresh token for the specified user.
    Payload contains sub (user_id), exp (expiry), jti (unique token ID), and type.
    """
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def verify_access_token(token: str) -> TokenPayload:
    """
    Validates a JWT access token and returns the decoded, validated payload.
    Raises ValueError for an expired or invalid token.
    """
    raw = _decode_token(token, ["sub", "role", "exp", "jti"])

    if raw.get("type") != "access":
        raise ValueError("Invalid token.")

    try:
        sub = uuid.UUID(raw["sub"])
        role = raw["role"]
        exp_claim = raw["exp"]
        jti = uuid.UUID(raw["jti"])

        exp = datetime.fromtimestamp(exp_claim, tz=UTC)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("Invalid token.") from e

    try:
        return TokenPayload(
            sub=sub,
            role=role,
            exp=exp,
            jti=jti,
        )
    except ValidationError as e:
        raise ValueError("Invalid token.") from e


def verify_refresh_token(token: str) -> RefreshTokenPayload:
    """
    Validates a JWT refresh token and returns the decoded, validated payload.
    Raises ValueError for an expired or invalid token.
    """
    raw = _decode_token(token, ["sub", "exp", "jti"])

    if raw.get("type") != "refresh":
        raise ValueError("Invalid token.")

    try:
        sub = uuid.UUID(raw["sub"])
        exp_claim = raw["exp"]
        jti = uuid.UUID(raw["jti"])
        exp = datetime.fromtimestamp(exp_claim, tz=UTC)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("Invalid token.") from e

    try:
        return RefreshTokenPayload(sub=sub, exp=exp, jti=jti)
    except ValidationError as e:
        raise ValueError("Invalid token.") from e


def get_pin_hash(pin: str) -> str:
    """
    Converts a plain-text PIN into a secure bcrypt hash.
    """
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pin.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """
    Verifies whether a plain-text PIN matches the hash stored in the database.
    """
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))

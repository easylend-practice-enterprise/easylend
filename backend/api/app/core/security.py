import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.token import TokenPayload


class RefreshTokenPayload(BaseModel):
    sub: uuid.UUID
    exp: datetime
    jti: uuid.UUID


def _decode_token(token: str, required_claims: list[str]) -> dict:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": required_claims},
        )
    except ExpiredSignatureError as e:
        raise ValueError("Token is verlopen.") from e
    except InvalidTokenError as e:
        raise ValueError("Ongeldige token.") from e


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """
    Maakt een ondertekende JWT access token aan voor de opgegeven gebruiker.
    Payload bevat sub (user_id), role, exp (verloopdatum) en jti (unieke token ID).
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    """
    Maakt een ondertekende JWT refresh token aan voor de opgegeven gebruiker.
    Payload bevat sub (user_id), exp (verloopdatum) en jti (unieke token ID).
    """
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def verify_access_token(token: str) -> TokenPayload:
    """
    Valideert een JWT access token en geeft de gedecodeerde en gevalideerde payload terug.
    Raises ValueError bij een verlopen of ongeldige token.
    """
    raw = _decode_token(token, ["sub", "role", "exp", "jti"])

    try:
        sub = uuid.UUID(raw["sub"])
        role = raw["role"]
        exp_claim = raw["exp"]
        jti = uuid.UUID(raw["jti"])

        # exp wordt door PyJWT normaal gesproken als UNIX timestamp (int) teruggegeven.
        exp = datetime.fromtimestamp(exp_claim, tz=UTC)
    except (KeyError, TypeError, ValueError) as e:
        # Onverwachte of malforme claimwaarden worden ook als ongeldig beschouwd.
        raise ValueError("Ongeldige token.") from e

    try:
        return TokenPayload(
            sub=sub,
            role=role,
            exp=exp,
            jti=jti,
        )
    except ValidationError as e:
        # Zorg dat ook Pydantic-validatiefouten als ongeldige token worden behandeld.
        raise ValueError("Ongeldige token.") from e


def verify_refresh_token(token: str) -> RefreshTokenPayload:
    """
    Valideert een JWT refresh token en geeft de gedecodeerde en gevalideerde payload terug.
    Raises ValueError bij een verlopen of ongeldige token.
    """
    raw = _decode_token(token, ["sub", "exp", "jti"])

    try:
        sub = uuid.UUID(raw["sub"])
        exp_claim = raw["exp"]
        jti = uuid.UUID(raw["jti"])
        exp = datetime.fromtimestamp(exp_claim, tz=UTC)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("Ongeldige token.") from e

    try:
        return RefreshTokenPayload(sub=sub, exp=exp, jti=jti)
    except ValidationError as e:
        raise ValueError("Ongeldige token.") from e


def get_pin_hash(pin: str) -> str:
    """
    Zet een plain-text PIN om naar een veilige bcrypt hash.
    """
    # bcrypt verwacht bytes, dus we encoden de string
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pin.encode("utf-8"), salt)

    # We returnen een string omdat de database (PostgreSQL) dit als VARCHAR opslaat
    return hashed_bytes.decode("utf-8")


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """
    Verifieert of een plain-text PIN overeenkomt met de hash uit de database.
    """
    # Zowel de input als de hash uit de DB moeten omgezet worden naar bytes voor de check
    return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_pin.encode("utf-8"))

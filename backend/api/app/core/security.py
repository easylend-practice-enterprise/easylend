import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings
from app.schemas.token import TokenPayload


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


def verify_access_token(token: str) -> TokenPayload:
    """
    Valideert een JWT access token en geeft de gedecrypteerde payload terug.
    Raises ValueError bij een verlopen of ongeldige token.
    """
    try:
        raw = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "role", "exp", "jti"]},
        )
    except ExpiredSignatureError as e:
        raise ValueError("Token is verlopen.") from e
    except InvalidTokenError as e:
        # Alle decode-/validatieproblemen van de token (incl. ontbrekende claims)
        # worden vertaald naar een generieke ValueError, zodat de caller een 401 kan sturen.
        raise ValueError("Ongeldige token.") from e

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

    return TokenPayload(
        sub=sub,
        role=role,
        exp=exp,
        jti=jti,
    )


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

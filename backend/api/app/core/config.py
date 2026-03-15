import os
import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_fallback_secret() -> str:
    """Genereert of leest een lokale fallback secret voor multi-worker consistentie."""
    fallback_file = ".dev_jwt_secret"
    if os.path.exists(fallback_file):
        with open(fallback_file) as f:
            return f.read().strip()

    new_secret = secrets.token_urlsafe(32)
    try:
        with open(fallback_file, "w") as f:
            f.write(new_secret)
    except OSError:
        pass  # Als we niet kunnen schrijven (bijv. in CI), gebruik gewoon de secret in memory
    return new_secret


class Settings(BaseSettings):
    PROJECT_NAME: str = "EasyLend API"
    # Fallback URLs voor lokale tests/CI. Gebruik in productie ALTIJD een .env bestand!
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = (
        "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db"
    )

    # JWT Configuration (ELP-22, ELP-82)
    # Als deze niet via env (.env of docker) wordt meegegeven, genereren we een veilige willekeurige sleutel.
    JWT_SECRET_KEY: str = Field(default_factory=_get_fallback_secret)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]

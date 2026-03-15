import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "EasyLend API"
    # Fallback URLs voor lokale tests/CI. Gebruik in productie ALTIJD een .env bestand!
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = (
        "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db"
    )

    # JWT Configuration (ELP-22, ELP-82)
    # Als deze niet via env (.env of docker) wordt meegegeven, genereren we een veilige willekeurige sleutel.
    # Let op: bij een willekeurige sleutel worden alle bestaande tokens ongeldig na een server-herstart!
    JWT_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]

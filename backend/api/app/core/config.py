from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Definieer de dummy secret 1 keer bovenaan
_DUMMY_SECRET = "insecure-local-dev-secret-key-123!"  # noqa: S105


class Settings(BaseSettings):
    PROJECT_NAME: str = "EasyLend API"
    ENVIRONMENT: str = "dev"

    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = (
        "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db"
    )

    # Gebruik de constante hier
    JWT_SECRET_KEY: str = _DUMMY_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """
        Zorgt ervoor dat de applicatie HARD crasht als we in productie draaien
        zonder een veilige JWT_SECRET_KEY mee te geven in de .env file.
        """
        if self.ENVIRONMENT.lower() in ("prod", "production"):
            # En gebruik de constante hier, Ruff zal nu zwijgen!
            if self.JWT_SECRET_KEY == _DUMMY_SECRET:
                raise ValueError(
                    "CRITICAL: JWT_SECRET_KEY ontbreekt in productie! "
                    "Start de server niet met de onveilige dev-fallback."
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]

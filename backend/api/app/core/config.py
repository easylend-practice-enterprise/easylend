import sys

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Define the dummy secret once at the top
_DUMMY_SECRET = "insecure-local-dev-secret-key-123!"  # noqa: S105


class Settings(BaseSettings):
    PROJECT_NAME: str = "EasyLend API"
    ENVIRONMENT: str = "dev"

    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = (
        "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db"
    )

    JWT_SECRET_KEY: str = _DUMMY_SECRET
    VISION_SERVICE_URL: str = "http://localhost:8001"
    VISION_API_KEY: str = _DUMMY_SECRET
    VISION_BOX_API_KEY: str = _DUMMY_SECRET
    SIMULATION_API_KEY: str = _DUMMY_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        """
        Ensures the application performs a HARD crash if dummy secrets are used
        in any environment other than explicitly "dev" or "test". This is a strict,
        fail-fast check to prevent accidental exposure of insecure defaults.

        Skips validation during Alembic migrations to avoid breaking DB utility scripts.
        """
        # Skip validation during Alembic migrations
        if sys.argv and "alembic" in sys.argv[0]:
            return self

        is_local_dev = self.ENVIRONMENT.lower() in ("dev", "test")

        if not is_local_dev:
            if (
                not self.JWT_SECRET_KEY
                or self.JWT_SECRET_KEY == _DUMMY_SECRET
                or len(self.JWT_SECRET_KEY) < 16
            ):
                raise ValueError(
                    "CRITICAL: JWT_SECRET_KEY is missing, insecure, or too short in a non-dev environment!"
                )
            if (
                not self.VISION_BOX_API_KEY
                or self.VISION_BOX_API_KEY == _DUMMY_SECRET
                or len(self.VISION_BOX_API_KEY) < 16
            ):
                raise ValueError(
                    "CRITICAL: VISION_BOX_API_KEY is missing, insecure, or too short in a non-dev environment!"
                )
            if (
                not self.SIMULATION_API_KEY
                or self.SIMULATION_API_KEY == _DUMMY_SECRET
                or len(self.SIMULATION_API_KEY) < 16
            ):
                raise ValueError(
                    "CRITICAL: SIMULATION_API_KEY is missing, insecure, or too short in a non-dev environment!"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]

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

    # Use the constant here
    JWT_SECRET_KEY: str = _DUMMY_SECRET
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
        """
        is_local_dev = self.ENVIRONMENT.lower() in ("dev", "test")

        if not is_local_dev:
            if self.JWT_SECRET_KEY == _DUMMY_SECRET:
                raise ValueError(
                    "CRITICAL: JWT_SECRET_KEY must be set in non-dev environments!"
                )
            if self.VISION_BOX_API_KEY == _DUMMY_SECRET:
                raise ValueError(
                    "CRITICAL: VISION_BOX_API_KEY must be set in non-dev environments!"
                )
            if self.SIMULATION_API_KEY == _DUMMY_SECRET:
                raise ValueError(
                    "CRITICAL: SIMULATION_API_KEY must be set in non-dev environments!"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]

import sys
from pathlib import Path

from pydantic import field_validator, model_validator
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
    # Absolute path to the upload directory. Defaults to ./uploads relative to
    # the app root (i.e. one level above the api/ directory). Can be overridden
    # via the UPLOAD_DIR environment variable.
    UPLOAD_DIR: Path = Path(__file__).parent.parent.parent / "uploads"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Comma-separated list of allowed CORS origins. Defaults to localhost for dev safety.
    # Override via CORS_ORIGINS env var (e.g. "https://app.example.com,https://admin.example.com").
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    # HTTP Basic Auth credentials for the interactive API docs.
    # Must be explicitly set via env vars in production (enforced below).
    DOCS_USERNAME: str | None = None
    DOCS_PASSWORD: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        """Accept a JSON list, a comma-separated string, or a plain list."""
        if isinstance(v, str):
            # Try JSON list first
            import json

            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            # Fall back to comma-separated
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        """
        Ensures the application performs a HARD crash if dummy secrets are used
        in any environment other than explicitly "dev" or "test". This is a strict,
        fail-fast check to prevent accidental exposure of insecure defaults.

        Skips validation during Alembic migrations to avoid breaking DB utility scripts.
        """
        # Skip validation during Alembic migrations
        if sys.argv and any("alembic" in arg for arg in sys.argv):
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
                not self.VISION_API_KEY
                or self.VISION_API_KEY == _DUMMY_SECRET
                or len(self.VISION_API_KEY) < 16
            ):
                raise ValueError(
                    "CRITICAL: VISION_API_KEY is missing, insecure, or too short in a non-dev environment!"
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

    @model_validator(mode="after")
    def validate_docs_credentials(self) -> "Settings":
        # Skip validation during Alembic migrations to avoid breaking DB utility scripts.
        if sys.argv and any("alembic" in arg for arg in sys.argv):
            return self

        env = (self.ENVIRONMENT or "").lower()
        if env in {"dev", "test"}:
            self.DOCS_USERNAME = self.DOCS_USERNAME or "admin"
            self.DOCS_PASSWORD = self.DOCS_PASSWORD or "easylend"
            return self

        if not self.DOCS_USERNAME or not self.DOCS_PASSWORD:
            raise ValueError(
                "DOCS_USERNAME and DOCS_PASSWORD must be explicitly set for non-dev/test environments."
            )

        forbidden_placeholders = {
            "admin",
            "easylend",
            "changeme",
            "password",
            "test",
            "user",
            "dummy_docs_user",
            "dummy_docs_password_do_not_use",
        }

        if self.DOCS_USERNAME.lower() in forbidden_placeholders:
            raise ValueError("DOCS_USERNAME is using a placeholder or weak value.")
        if self.DOCS_PASSWORD.lower() in forbidden_placeholders:
            raise ValueError("DOCS_PASSWORD is using a placeholder or weak value.")
        if len(self.DOCS_PASSWORD) < 12:
            raise ValueError(
                "DOCS_PASSWORD must be at least 12 characters long in non-dev environments."
            )
        if self.DOCS_USERNAME == self.DOCS_PASSWORD:
            raise ValueError("DOCS_PASSWORD must not be identical to DOCS_USERNAME.")

        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]

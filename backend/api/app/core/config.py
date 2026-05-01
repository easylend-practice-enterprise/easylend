import sys
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Define the dummy secret once at the top
_DUMMY_SECRET = "insecure-local-dev-secret-key-123!"  # noqa: S105


class Settings(BaseSettings):
    PROJECT_NAME: str = Field(
        default="EasyLend API",
        description="Human-readable service name used in API docs and UI.",
    )
    PROJECT_DESCRIPTION: str = Field(
        default="Core Backend for the EasyLend Practice Enterprise",
        description="OpenAPI description text for this service.",
    )
    PROJECT_VERSION: str = Field(
        default="1.0.0",
        description="Application version exposed in OpenAPI metadata.",
    )
    ENVIRONMENT: str = Field(
        default="dev",
        description="Deployment environment identifier (e.g. dev/test/prod).",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://test_user:test_password@localhost:5432/test_db",
        description="Async SQLAlchemy database connection string.",
    )
    DB_POOL_SIZE: int = Field(
        default=20,
        ge=1,
        description="Base size of the SQLAlchemy async DB connection pool.",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=30,
        ge=0,
        description="Maximum overflow connections above DB_POOL_SIZE.",
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30,
        ge=1,
        description="Seconds to wait before failing DB pool checkout.",
    )
    DB_POOL_RECYCLE: int = Field(
        default=1800,
        ge=1,
        description="Seconds before DB connections are recycled.",
    )

    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string used for cache, rate limit, and locks.",
    )
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS: float = Field(
        default=2.0,
        gt=0,
        description="Redis socket connect timeout in seconds.",
    )
    REDIS_SOCKET_TIMEOUT_SECONDS: float = Field(
        default=3.0,
        gt=0,
        description="Redis socket read/write timeout in seconds.",
    )

    JWT_SECRET_KEY: str = Field(
        default=_DUMMY_SECRET,
        description="JWT signing key for access/refresh tokens.",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing algorithm.",
    )
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        ge=1,
        description="Access token lifetime in minutes.",
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        ge=1,
        description="Refresh token lifetime in days.",
    )
    AUTH_MAX_LOGIN_ATTEMPTS: int = Field(
        default=5,
        ge=1,
        description="Maximum failed PIN attempts before account lockout.",
    )
    AUTH_LOCKOUT_MINUTES: int = Field(
        default=15,
        ge=1,
        description="Minutes an account remains locked after max failed attempts.",
    )

    VISION_SERVICE_URL: str = Field(
        default="http://localhost:8001",
        description="Base URL of the Vision service.",
    )
    VISION_API_KEY: str = Field(
        default=_DUMMY_SECRET,
        description="Bearer token used by API -> Vision service calls.",
    )
    VISION_API_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        gt=0,
        description="HTTP timeout for Vision service requests in seconds.",
    )
    VISION_MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        description="Maximum accepted image upload size for vision analyze endpoint.",
    )
    VISION_BOX_API_KEY: str = Field(
        default=_DUMMY_SECRET,
        description="Shared device token for hardware Vision Box clients.",
    )
    SIMULATION_API_KEY: str = Field(
        default=_DUMMY_SECRET,
        description="Shared device token for hardware simulator clients.",
    )

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins (JSON array or comma-separated env value).",
    )
    CORS_MAX_AGE_SECONDS: int = Field(
        default=600,
        ge=0,
        description="Seconds browsers may cache CORS preflight responses.",
    )

    DOCS_CONTENT_SECURITY_POLICY: str = Field(
        default=(
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; "
            "font-src 'self' https://cdn.jsdelivr.net data:;"
        ),
        description="Content-Security-Policy header for /docs, /redoc, and /openapi.json.",
    )
    DEFAULT_CONTENT_SECURITY_POLICY: str = Field(
        default=(
            "default-src 'self'; script-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self';"
        ),
        description="Default Content-Security-Policy header for non-doc endpoints.",
    )
    PERMISSIONS_POLICY_HEADER: str = Field(
        default="camera=(), microphone=(), geolocation=(), payment=()",
        description="Permissions-Policy header value.",
    )

    RATE_LIMIT_IP_LIMIT: int = Field(
        default=500,
        ge=1,
        description="Allowed public requests per IP within RATE_LIMIT_IP_WINDOW_SECONDS.",
    )
    RATE_LIMIT_IP_WINDOW_SECONDS: int = Field(
        default=60,
        ge=1,
        description="Window size in seconds for IP-based rate limiting.",
    )
    RATE_LIMIT_TOKEN_LIMIT: int = Field(
        default=60,
        ge=1,
        description="Allowed authenticated requests per subject in token window.",
    )
    RATE_LIMIT_TOKEN_WINDOW_SECONDS: int = Field(
        default=60,
        ge=1,
        description="Window size in seconds for token-based rate limiting.",
    )

    IDEMPOTENCY_TTL_SECONDS: int = Field(
        default=86400,
        ge=1,
        description="TTL in seconds for idempotency keys.",
    )
    IDEMPOTENCY_MAX_KEY_LENGTH: int = Field(
        default=256,
        ge=1,
        description="Maximum accepted length of Idempotency-Key header value.",
    )

    KIOSK_WS_MAX_CONNECTIONS: int = Field(
        default=100,
        ge=1,
        description="Global websocket connection limit for kiosk clients.",
    )
    KIOSK_PRESENCE_TTL_SECONDS: int = Field(
        default=30,
        ge=1,
        description="Redis presence key TTL for kiosk online status.",
    )
    KIOSK_PRESENCE_REFRESH_SECONDS: int = Field(
        default=10,
        ge=1,
        description="Seconds between kiosk presence heartbeat updates.",
    )
    KIOSK_COMMAND_SEND_TIMEOUT_SECONDS: float = Field(
        default=3.0,
        gt=0,
        description="Timeout in seconds when forwarding a command to kiosk websocket.",
    )
    KIOSK_PUBSUB_POLL_TIMEOUT_SECONDS: float = Field(
        default=1.0,
        gt=0,
        description="Redis pubsub get_message polling timeout in seconds.",
    )
    KIOSK_PUBSUB_IDLE_SLEEP_SECONDS: float = Field(
        default=0.05,
        gt=0,
        description="Idle sleep between empty pubsub polls in seconds.",
    )

    LOAN_TIMEOUT_WORKER_TIMEOUT_MINUTES: int = Field(
        default=3,
        ge=1,
        description="Minutes after RESERVED/RETURNING activity before timeout processing.",
    )
    LOAN_TIMEOUT_WORKER_INTERVAL_SECONDS: int = Field(
        default=60,
        ge=1,
        description="Polling interval in seconds for the loan-timeout worker.",
    )
    LOAN_TIMEOUT_WORKER_BATCH_SIZE: int = Field(
        default=100,
        ge=1,
        description="Batch size used by loan-timeout worker when querying IDs.",
    )
    LOAN_TIMEOUT_WORKER_LOCK_TTL_SECONDS: int = Field(
        default=55,
        ge=1,
        description="Distributed lock TTL in seconds for the loan-timeout worker.",
    )

    OVERDUE_WORKER_INTERVAL_HOURS: int = Field(
        default=1,
        ge=1,
        description="Polling interval in hours for the overdue worker.",
    )
    OVERDUE_WORKER_BATCH_SIZE: int = Field(
        default=100,
        ge=1,
        description="Batch size used by overdue worker when querying IDs.",
    )
    OVERDUE_WORKER_LOCK_TTL_SECONDS: int = Field(
        default=3500,
        ge=1,
        description="Distributed lock TTL in seconds for overdue worker execution.",
    )

    # Absolute path to the upload directory. Defaults to ./uploads relative to
    # the app root (i.e. one level above the api/ directory). Can be overridden
    # via the UPLOAD_DIR environment variable.
    UPLOAD_DIR: Path = Field(
        default=Path(__file__).parent.parent.parent / "uploads",
        description="Absolute path where uploaded images are persisted.",
    )
    # HTTP Basic Auth credentials for the interactive API docs.
    # Must be explicitly set via env vars in production (enforced below).
    DOCS_USERNAME: str | None = Field(
        default=None,
        description="HTTP basic auth username for /docs and /redoc.",
    )
    DOCS_PASSWORD: str | None = Field(
        default=None,
        description="HTTP basic auth password for /docs and /redoc.",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> Any:
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

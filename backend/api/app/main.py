from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.router import router as v1_router
from app.api.ws import ws_router
from app.core.config import settings
from app.core.uploads import UPLOAD_DIR

# Redis imports
from app.db.redis import (
    check_redis_connection,
    redis_client,
)
from app.workers.loan_timeout_worker import (
    start_reserved_loan_timeout_worker,
    stop_reserved_loan_timeout_worker,
)
from app.workers.overdue_worker import (
    start_overdue_worker,
    stop_overdue_worker,
)

# ---------------------------------------------------------------------------
# Security middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects hardened HTTP security headers on every response.

    Applies a defence-in-depth posture even when individual routes
    do not explicitly set them.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # Framing / clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Referrer policy: don't leak referrer on external navigation
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # XSS filter (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Content Security Policy — allows Swagger UI assets from jsdelivr CDN
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com;"
        )
        # Permissions policy: disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Avoid touching the real Redis client during tests (prevents background
    # async tasks from being created which can raise un-retrieved Future
    # exceptions). Only check Redis in non-test environments.
    if settings.ENVIRONMENT.lower() != "test":
        await check_redis_connection()
    timeout_worker_task = None
    timeout_worker_stop_event = None
    overdue_worker_task = None
    overdue_worker_stop_event = None
    if settings.ENVIRONMENT.lower() != "test":
        timeout_worker_task, timeout_worker_stop_event = (
            start_reserved_loan_timeout_worker()
        )
        overdue_worker_task, overdue_worker_stop_event = start_overdue_worker()
    # Ensure runtime uploads directory exists (create at startup, not at import time)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
    if (
        settings.ENVIRONMENT.lower() != "test"
        and timeout_worker_task is not None
        and timeout_worker_stop_event is not None
    ):
        await stop_reserved_loan_timeout_worker(
            timeout_worker_task,
            timeout_worker_stop_event,
        )
    if (
        settings.ENVIRONMENT.lower() != "test"
        and overdue_worker_task is not None
        and overdue_worker_stop_event is not None
    ):
        await stop_overdue_worker(
            overdue_worker_task,
            overdue_worker_stop_event,
        )
    # Close Redis client only outside of tests to avoid background-transport
    # shutdown races during pytest session teardown.
    if settings.ENVIRONMENT.lower() != "test":
        await redis_client.aclose()


app = FastAPI(
    title="EasyLend API",
    description="Core Backend for the EasyLend Practice Enterprise",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: allow credential-free cross-origin calls from known web origins only.
# Restrict allowed_origins to your actual frontend domains in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # No credentials over wildcard origins
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
    max_age=600,  # Browser may cache preflight for 10 minutes
)

app.add_middleware(SecurityHeadersMiddleware)


@app.get("/")
async def read_root():
    return {"message": "Welcome to the EasyLend API!", "docs_url": "/docs"}


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "components": {"api": "ok"}}


app.include_router(v1_router)
app.include_router(ws_router)

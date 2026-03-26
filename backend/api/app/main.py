from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Avoid touching the real Redis client during tests (prevents background
    # async tasks from being created which can raise un-retrieved Future
    # exceptions). Only check Redis in non-test environments.
    if settings.ENVIRONMENT != "test":
        await check_redis_connection()
    timeout_worker_task = None
    timeout_worker_stop_event = None
    if settings.ENVIRONMENT != "test":
        timeout_worker_task, timeout_worker_stop_event = (
            start_reserved_loan_timeout_worker()
        )
    # Ensure runtime uploads directory exists (create at startup, not at import time)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
    if (
        settings.ENVIRONMENT != "test"
        and timeout_worker_task is not None
        and timeout_worker_stop_event is not None
    ):
        await stop_reserved_loan_timeout_worker(
            timeout_worker_task,
            timeout_worker_stop_event,
        )
    # Close Redis client only outside of tests to avoid background-transport
    # shutdown races during pytest session teardown.
    if settings.ENVIRONMENT != "test":
        await redis_client.aclose()


app = FastAPI(
    title="EasyLend API",
    description="Core Backend for the EasyLend Practice Enterprise",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def read_root():
    return {"message": "Welcome to the EasyLend API!", "docs_url": "/docs"}


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "components": {"api": "ok"}}


app.include_router(v1_router)
app.include_router(ws_router)

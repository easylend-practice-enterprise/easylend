from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI

from app.api.v1.router import router as v1_router

# Redis imports
from app.db.redis import (
    check_redis_connection,
    redis_client,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    await check_redis_connection()
    # Ensure uploads directory exists if enabled
    from app.core.config import settings as _settings

    if getattr(_settings, "UPLOADS_ENABLED", True):
        with suppress(Exception):
            Path(_settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
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

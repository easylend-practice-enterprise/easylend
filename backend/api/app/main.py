from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.api.ws import ws_router

# Redis imports
from app.db.redis import (
    check_redis_connection,
    redis_client,
)

# Runtime uploads directory used by endpoints that save files
UPLOAD_DIR = Path("uploads")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await check_redis_connection()
    # Ensure runtime uploads directory exists (create at startup, not at import time)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
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
app.include_router(ws_router)

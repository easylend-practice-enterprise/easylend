from contextlib import asynccontextmanager
from fastapi import FastAPI

# Redis imports
from app.db.redis import (
    check_redis_connection,
    redis_client,
    set_refresh_token,
    get_refresh_token,
    delete_refresh_token,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await check_redis_connection()
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
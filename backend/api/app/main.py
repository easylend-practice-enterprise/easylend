from contextlib import asynccontextmanager
from fastapi import FastAPI

# Voeg je nieuwe functies toe aan de import:
from app.db.redis import (
    check_redis_connection,
    redis_client,
    set_refresh_token,
    get_refresh_token,
    delete_refresh_token,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dingen die hier staan gebeuren bij het OPSTARTEN
    await check_redis_connection()
    yield
    # Dingen die hier staan gebeuren bij het AFSLUITEN
    await redis_client.aclose()


# Koppel de lifespan aan je app
app = FastAPI(title="EasyLend API", lifespan=lifespan)


@app.get("/")
def read_root():
    return {"message": "Welcome to the EasyLend API!", "docs_url": "/docs"}


@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy", "components": {"api": "ok"}}

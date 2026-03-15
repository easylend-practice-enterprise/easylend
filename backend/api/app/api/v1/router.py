from fastapi import APIRouter

from app.api.v1.endpoints import auth

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)

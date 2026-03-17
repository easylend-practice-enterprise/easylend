from fastapi import APIRouter

from app.api.v1.endpoints import auth, equipment, roles, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(roles.router)
router.include_router(users.router)
router.include_router(equipment.categories_router)
router.include_router(equipment.kiosks_router)
router.include_router(equipment.lockers_router)
router.include_router(equipment.assets_router)

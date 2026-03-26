from fastapi import APIRouter

from app.api.v1.endpoints import auth, equipment, images, loans, roles, users, vision

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(roles.router)
router.include_router(users.router)
router.include_router(equipment.categories_router)
router.include_router(equipment.kiosks_router)
router.include_router(equipment.lockers_router)
router.include_router(equipment.catalog_router)
router.include_router(equipment.assets_router)
router.include_router(loans.router)
router.include_router(vision.router)
router.include_router(vision.webhook_router)
router.include_router(images.router)

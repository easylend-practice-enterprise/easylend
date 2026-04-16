import asyncio
import logging
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent


def _prepare_runtime() -> None:
    """Make backend/api importable and resolve local environment files."""
    os.chdir(_SCRIPT_DIR)

    script_dir = str(_SCRIPT_DIR)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)


logger = logging.getLogger(__name__)


async def get_or_create(session, model, defaults=None, update_existing=False, **kwargs):
    """Retrieves an existing record or creates a new one. Updates the existing record if required."""
    from sqlalchemy import select

    result = await session.execute(select(model).filter_by(**kwargs))
    instances = result.scalars().all()

    if len(instances) > 1:
        raise RuntimeError(
            f"Multiple records found for {model.__name__} with filter {kwargs}. "
            "Ensure the seed data is unique."
        )

    if len(instances) == 1:
        instance = instances[0]
        if defaults and update_existing:
            for key, value in defaults.items():
                setattr(instance, key, value)
        return instance, False

    params = dict((k, v) for k, v in kwargs.items())
    if defaults:
        params.update(defaults)

    instance = model(**params)
    session.add(instance)
    await session.flush()
    return instance, True


async def seed_database():
    _prepare_runtime()

    from sqlalchemy import or_, select

    from app.core.security import get_pin_hash
    from app.db.database import AsyncSessionLocal
    from app.db.models import (
        Asset,
        AssetStatus,
        Category,
        Kiosk,
        KioskStatus,
        Locker,
        LockerStatus,
        Role,
        User,
    )

    logger.info("Starting database seeding.")

    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                roles_to_create = ["ADMIN", "USER", "KIOSK"]
                admin_role = None
                for role_name in roles_to_create:
                    role, created = await get_or_create(
                        session, Role, role_name=role_name
                    )
                    if created:
                        logger.info(f"Role created: {role_name}")
                    if role_name == "ADMIN":
                        admin_role = role

                cats_to_create = ["Laptops", "Tablets"]
                laptop_cat = None
                for cat_name in cats_to_create:
                    cat, created = await get_or_create(
                        session, Category, category_name=cat_name
                    )
                    if created:
                        logger.info(f"Category created: {cat_name}")
                    if cat_name == "Laptops":
                        laptop_cat = cat

                kiosk, created = await get_or_create(
                    session,
                    Kiosk,
                    defaults={
                        "location_description": "Main entrance hall, next to the reception desk",
                        "kiosk_status": KioskStatus.ONLINE,
                    },
                    update_existing=True,
                    name="Main Building A",
                )
                if created:
                    logger.info("Kiosk created: Main Building A")

                for logical_num, status in [
                    (1, LockerStatus.OCCUPIED),
                    (2, LockerStatus.AVAILABLE),
                    (3, LockerStatus.AVAILABLE),
                ]:
                    locker, created = await get_or_create(
                        session,
                        Locker,
                        defaults={"locker_status": status},
                        update_existing=True,
                        kiosk_id=kiosk.kiosk_id,
                        logical_number=logical_num,
                    )
                    if created:
                        logger.info(f"Locker created. Logical number: {logical_num}")

                if not admin_role:
                    raise RuntimeError(
                        "Admin role is missing. Cannot create the admin user."
                    )

                admin_pin = os.getenv("ADMIN_DEFAULT_PIN", "123456")
                admin_email = os.getenv("ADMIN_DEFAULT_EMAIL", "admin@easylend.be")
                admin_nfc = "NFC-ADMIN-001"

                result = await session.execute(
                    select(User).where(
                        or_(User.email == admin_email, User.nfc_tag_id == admin_nfc)
                    )
                )
                admin_users = result.scalars().all()

                if len(admin_users) > 1:
                    raise RuntimeError(
                        "Multiple admin users found with the same email or NFC tag. "
                        "Resolve this conflict before re-seeding."
                    )

                admin_user = admin_users[0] if admin_users else None

                if admin_user:
                    admin_user.email = admin_email
                    admin_user.nfc_tag_id = admin_nfc
                    admin_user.role_id = admin_role.role_id
                    admin_user.first_name = "Admin"
                    admin_user.last_name = "EasyLend"
                    admin_user.pin_hash = get_pin_hash(admin_pin)
                    created = False
                else:
                    admin_user = User(
                        email=admin_email,
                        nfc_tag_id=admin_nfc,
                        role_id=admin_role.role_id,
                        first_name="Admin",
                        last_name="EasyLend",
                        pin_hash=get_pin_hash(admin_pin),
                    )
                    session.add(admin_user)
                    created = True

                if created:
                    logger.info(f"Admin user created: {admin_email}")

                locker1, _ = await get_or_create(
                    session, Locker, kiosk_id=kiosk.kiosk_id, logical_number=1
                )

                if not laptop_cat or not locker1:
                    raise RuntimeError(
                        "Category or Locker is missing. Cannot create the seed asset."
                    )

                asset, created = await get_or_create(
                    session,
                    Asset,
                    defaults={
                        "category_id": laptop_cat.category_id,
                        "locker_id": locker1.locker_id,
                        "name": "Dell XPS 15",
                        "asset_status": AssetStatus.AVAILABLE,
                    },
                    update_existing=True,
                    aztec_code="AZ-LAP-001",
                )
                if created:
                    logger.info("Asset created: Dell XPS 15")

            logger.info("Database seeding completed successfully.")

        except Exception:
            logger.exception("An error occurred during seeding")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        asyncio.run(seed_database())
    except Exception:
        sys.exit(1)

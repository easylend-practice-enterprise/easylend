import asyncio
import logging
import os
import sys

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

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

logger = logging.getLogger(__name__)


async def get_or_create(session, model, defaults=None, **kwargs):
    """Helper functie om een bestaand record op te halen of een nieuwe aan te maken if not exists."""
    # Copilot Fix 2: Check voor exacte matches en voorkom silent errors bij duplicaten
    result = await session.execute(select(model).filter_by(**kwargs))
    instances = result.scalars().all()

    if len(instances) > 1:
        raise RuntimeError(
            f"get_or_create vond meerdere records voor {model.__name__} "
            f"met filter {kwargs}. Zorg voor unieke data of los duplicaten op."
        )

    if len(instances) == 1:
        return instances[0], False

    params = dict((k, v) for k, v in kwargs.items())
    if defaults:
        params.update(defaults)

    instance = model(**params)
    session.add(instance)
    await session.flush()
    return instance, True


async def seed_database():
    env = os.getenv("ENVIRONMENT", "production").lower()
    if env != "development":
        # Copilot Fix 1: Duidelijke instructies voor de developer
        raise RuntimeError(
            f"Veiligheidsblokkade: Seeding is alleen toegestaan in 'development' (huidig: {env}).\n"
            "Stel de omgevingsvariabele ENVIRONMENT in op 'development' om lokaal te seeden.\n"
            'In PowerShell:  $env:ENVIRONMENT="development"; uv run python seed.py\n'
            "In Bash/Zsh:    ENVIRONMENT=development uv run python seed.py"
        )

    logger.info("🌱 Starten met seeden van de database...")

    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                # --- STAP 1: ROLES ---
                roles_to_create = ["Admin", "Kiosk", "User"]
                admin_role = None
                for role_name in roles_to_create:
                    role, created = await get_or_create(
                        session, Role, role_name=role_name
                    )
                    if created:
                        logger.info(f"✅ Rol aangemaakt: {role_name}")
                    if role_name == "Admin":
                        admin_role = role

                # --- STAP 2: CATEGORIES ---
                cats_to_create = ["Laptops", "Tablets"]
                laptop_cat = None
                for cat_name in cats_to_create:
                    cat, created = await get_or_create(
                        session, Category, category_name=cat_name
                    )
                    if created:
                        logger.info(f"✅ Categorie aangemaakt: {cat_name}")
                    if cat_name == "Laptops":
                        laptop_cat = cat

                # --- STAP 3: KIOSKS ---
                kiosk, created = await get_or_create(
                    session,
                    Kiosk,
                    defaults={
                        "location_description": "Inkomhal naast de receptie",
                        "kiosk_status": KioskStatus.ONLINE,
                    },
                    name="Hoofdgebouw A",
                )
                if created:
                    logger.info("✅ Kiosk aangemaakt: Hoofdgebouw A")

                # --- STAP 4: LOCKERS ---
                for logical_num, status in [
                    (1, LockerStatus.OCCUPIED),
                    (2, LockerStatus.AVAILABLE),
                    (3, LockerStatus.AVAILABLE),
                ]:
                    locker, created = await get_or_create(
                        session,
                        Locker,
                        defaults={"locker_status": status},
                        kiosk_id=kiosk.kiosk_id,
                        logical_number=logical_num,
                    )
                    if created:
                        logger.info(f"✅ Locker aangemaakt: Logical nr {logical_num}")

                # --- STAP 5: USERS ---
                if not admin_role:
                    raise RuntimeError("Admin rol mist! Kan gebruiker niet aanmaken.")

                admin_pin = os.getenv("ADMIN_DEFAULT_PIN", "123456")
                admin_email = os.getenv("ADMIN_DEFAULT_EMAIL", "admin@easylend.be")
                admin_nfc = "NFC-ADMIN-001"

                # Copilot Fix 3: Zoek op Email OF NFC tag (Upsert logica)
                result = await session.execute(
                    select(User).where(
                        or_(User.email == admin_email, User.nfc_tag_id == admin_nfc)
                    )
                )
                admin_user = result.scalars().first()

                if admin_user:
                    # Update bestaande gebruiker
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
                    logger.info(f"✅ Admin user aangemaakt ({admin_email}).")

                # --- STAP 6: ASSETS ---
                locker1, _ = await get_or_create(
                    session, Locker, kiosk_id=kiosk.kiosk_id, logical_number=1
                )

                if not laptop_cat or not locker1:
                    raise RuntimeError(
                        "Categorie of Locker mist! Kan asset niet aanmaken."
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
                    aztec_code="AZ-LAP-001",
                )
                if created:
                    logger.info("✅ Asset aangemaakt: Dell XPS 15")

            logger.info("🚀 Database seeding voltooid!")

        except SQLAlchemyError as e:
            logger.error(f"❌ Database error tijdens seeding: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Onverwachte fout tijdens seeding: {e}")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        asyncio.run(seed_database())
    except Exception:
        sys.exit(1)

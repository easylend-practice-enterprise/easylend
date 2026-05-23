import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import or_, select, text

# ---------------------------------------------------------------------------
# Runtime Preparation
# ---------------------------------------------------------------------------

# Resolve the backend/api directory as the application root
_SCRIPT_DIR = Path(__file__).resolve().parent.parent


def _prepare_runtime() -> None:
    """Ensure we can import from 'app' and load settings from the correct dir."""
    os.chdir(_SCRIPT_DIR)
    script_dir = str(_SCRIPT_DIR)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)


_prepare_runtime()

# Now we can import app components
from app.core.config import settings  # noqa: E402
from app.core.security import get_pin_hash, hash_nfc_tag  # noqa: E402
from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.models import Role, User, UserStatus  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bootstrap")

ADMIN_EMAIL = os.getenv("ADMIN_DEFAULT_EMAIL", "admin@easylend.be")
ADMIN_PIN = os.getenv("ADMIN_DEFAULT_PIN", "123456")
ADMIN_NFC = os.getenv("ADMIN_DEFAULT_NFC", "NFC-ADMIN-001")


# ---------------------------------------------------------------------------
# Core Utilities
# ---------------------------------------------------------------------------


async def purge_database():
    """
    DANGEROUS: Wipes all business data from the database.
    Only to be used in development or for a fresh location initialization.
    """
    logger.warning("!!! DATABASE PURGE INITIATED !!!")

    if settings.ENVIRONMENT.lower() in ["prod", "production"]:
        logger.error("PURGE BLOCKED: Cannot purge a production environment.")
        return False

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Order is important to avoid FK violations if CASCADE is not used,
            # but we use CASCADE for completeness and safety across all engines.
            tables = [
                "audit_logs",
                "damage_reports",
                "ai_evaluations",
                "loans",
                "assets",
                "lockers",
                "kiosks",
                "users",
                "categories",
            ]
            truncate_stmt = f"TRUNCATE TABLE {', '.join(tables)} CASCADE;"
            await session.execute(text(truncate_stmt))
            logger.info(f"Successfully truncated tables: {', '.join(tables)}")
    return True


async def bootstrap_admin():
    """
    Ensures that the basic roles and at least one Admin user exist.
    This is the absolute minimum requirement for a new production instance.
    """
    logger.info("Starting Production Bootstrap...")
    logger.info("Ensuring roles and admin user exist in the database...")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Ensure Roles exist
            roles_to_create = ["ADMIN", "USER", "KIOSK"]
            role_map = {}
            for role_name in roles_to_create:
                res = await session.execute(select(Role).filter_by(role_name=role_name))
                role = res.scalar_one_or_none()
                if not role:
                    role = Role(role_name=role_name)
                    session.add(role)
                    await session.flush()
                    logger.info(f"Created missing role: {role_name}")
                role_map[role_name] = role

            # 2. Ensure Bootstrap Admin User exists
            hashed_nfc = hash_nfc_tag(ADMIN_NFC)

            # Check by email or NFC to avoid duplicates
            res = await session.execute(
                select(User).where(
                    or_(User.email == ADMIN_EMAIL, User.nfc_tag_id == hashed_nfc)
                )
            )
            admin = res.scalar_one_or_none()

            if not admin:
                admin = User(
                    email=ADMIN_EMAIL,
                    nfc_tag_id=hashed_nfc,
                    role_id=role_map["ADMIN"].role_id,
                    first_name="Admin",
                    last_name="EasyLend",
                    pin_hash=get_pin_hash(ADMIN_PIN),
                    status=UserStatus.ACTIVE,
                    accepted_privacy_policy=True,
                )
                session.add(admin)
                logger.info(f"Created bootstrap admin user: {ADMIN_EMAIL}")
            else:
                # Ensure existing admin has the expected credentials
                admin.email = ADMIN_EMAIL
                admin.nfc_tag_id = hashed_nfc
                admin.pin_hash = get_pin_hash(ADMIN_PIN)
                admin.role_id = role_map["ADMIN"].role_id
                admin.status = UserStatus.ACTIVE
                admin.accepted_privacy_policy = True
                logger.info(f"Updated existing admin user: {ADMIN_EMAIL}")

    logger.info("Bootstrap successful. The system is now ready for management.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EasyLend Production Bootstrap")
    parser.add_argument(
        "--force-purge",
        action="store_true",
        help="DANGEROUS: Wipes all existing data before bootstrapping.",
    )

    args = parser.parse_args()

    async def run():
        try:
            if args.force_purge:
                success = await purge_database()
                if not success:
                    sys.exit(1)
            await bootstrap_admin()
        except Exception:
            logger.exception("A critical error occurred during bootstrap")
            sys.exit(1)

    asyncio.run(run())

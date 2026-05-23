import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

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

# Now we can import app components and the bootstrap logic
from app.core.audit import log_audit_event  # noqa: E402
from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.models import (  # noqa: E402
    AIEvaluation,
    Asset,
    AssetStatus,
    DamageReport,
    EvaluationType,
    Kiosk,
    Loan,
    LoanStatus,
    Locker,
    LockerStatus,
    User,
)
from app.main import app  # noqa: E402
from scripts.bootstrap import bootstrap_admin, purge_database  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_dev")

# These can be overridden via environment variables
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
ADMIN_EMAIL = os.getenv("ADMIN_DEFAULT_EMAIL", "admin@easylend.be")
ADMIN_PIN = os.getenv("ADMIN_DEFAULT_PIN", "123456")
ADMIN_NFC = os.getenv("ADMIN_DEFAULT_NFC", "NFC-ADMIN-001")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_user_id_by_email(session, email: str) -> UUID:
    res = await session.execute(select(User.user_id).where(User.email == email))
    val = res.scalar_one_or_none()
    if not val:
        raise RuntimeError(f"User {email} not found")
    return val


async def get_asset_id_by_code(session, code: str) -> UUID:
    res = await session.execute(select(Asset.asset_id).where(Asset.aztec_code == code))
    val = res.scalar_one_or_none()
    if not val:
        raise RuntimeError(f"Asset {code} not found")
    return val


# ---------------------------------------------------------------------------
# Phase 2: Seeding (via API)
# ---------------------------------------------------------------------------


async def seed_master_data():
    """
    Populates the database with master data using the API endpoints.
    """
    logger.info("--- Phase 2: Seeding Master Data via API ---")

    transport = None
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.get(f"{API_BASE_URL}/health")
        logger.info(f"Using live API server at {API_BASE_URL}")
    except Exception:
        logger.info(
            "No live API server detected. Using ASGITransport (direct internal calls)."
        )
        transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url=API_BASE_URL) as client:
        # 1. Login
        logger.info(f"Logging in as {ADMIN_EMAIL}...")
        login_resp = await client.post(
            "/auth/pin", json={"nfc_tag_id": ADMIN_NFC, "pin": ADMIN_PIN}
        )
        if login_resp.status_code != 200:
            logger.error(f"Login failed: {login_resp.status_code} - {login_resp.text}")
            return

        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Categories
        logger.info("Seeding Categories...")
        categories = ["Laptops", "Tablets", "Cameras", "Audio", "Accessories"]
        cat_map = {}
        for cat_name in categories:
            resp = await client.post(
                "/categories", json={"category_name": cat_name}, headers=headers
            )
            if resp.status_code == 201:
                cat_map[cat_name] = resp.json()["category_id"]
                logger.info(f"  + Category: {cat_name}")
            else:
                list_resp = await client.get("/categories", headers=headers)
                for item in list_resp.json()["items"]:
                    if item["category_name"] == cat_name:
                        cat_map[cat_name] = item["category_id"]
                        break

        # 3. Kiosks
        logger.info("Seeding Kiosks...")
        kiosks = [
            {"name": "Main Building A", "loc": "Entrance hall"},
            {"name": "Library", "loc": "Study zone, 1st floor"},
            {"name": "Science Lab", "loc": "Basement corridor"},
        ]
        kiosk_ids = []
        for k in kiosks:
            resp = await client.post(
                "/kiosks",
                json={
                    "name": k["name"],
                    "location_description": k["loc"],
                    "kiosk_status": "ONLINE",
                },
                headers=headers,
            )
            if resp.status_code == 201:
                kiosk_ids.append(resp.json()["kiosk_id"])
                logger.info(f"  + Kiosk: {k['name']}")
            else:
                list_resp = await client.get("/kiosks", headers=headers)
                for item in list_resp.json()["items"]:
                    if item["name"] == k["name"]:
                        kiosk_ids.append(item["kiosk_id"])
                        break

        # 4. Lockers (12 per kiosk)
        logger.info("Seeding Lockers...")
        all_locker_ids = []
        for kid in kiosk_ids:
            for i in range(1, 13):
                resp = await client.post(
                    "/lockers",
                    json={
                        "kiosk_id": kid,
                        "logical_number": i,
                        "locker_status": "AVAILABLE",
                    },
                    headers=headers,
                )
                if resp.status_code == 201:
                    all_locker_ids.append(resp.json()["locker_id"])
                else:
                    # Find existing
                    list_resp = await client.get(
                        f"/kiosks/{kid}/lockers", headers=headers
                    )
                    for item in list_resp.json()["items"]:
                        if item["logical_number"] == i:
                            all_locker_ids.append(item["locker_id"])
                            break
        logger.info(f"  Total lockers: {len(all_locker_ids)}")

        # 5. Assets
        logger.info("Seeding Assets...")
        assets_to_seed = [
            # Laptops
            {"name": "Dell XPS 15 (2024)", "code": "AZ-LAP-001", "cat": "Laptops"},
            {"name": "Dell XPS 15 (2024)", "code": "AZ-LAP-002", "cat": "Laptops"},
            {"name": "MacBook Air M3", "code": "AZ-LAP-003", "cat": "Laptops"},
            {"name": "Lenovo ThinkPad X1", "code": "AZ-LAP-004", "cat": "Laptops"},
            # Tablets
            {"name": 'iPad Pro 12.9"', "code": "AZ-TAB-001", "cat": "Tablets"},
            {"name": "iPad Air", "code": "AZ-TAB-002", "cat": "Tablets"},
            {"name": "Samsung Galaxy Tab S9", "code": "AZ-TAB-003", "cat": "Tablets"},
            # Cameras
            {"name": "Sony A7 IV", "code": "AZ-CAM-001", "cat": "Cameras"},
            {"name": "Canon EOS R6", "code": "AZ-CAM-002", "cat": "Cameras"},
            {"name": "Fujifilm X-T5", "code": "AZ-CAM-003", "cat": "Cameras"},
            # Audio
            {"name": "Jabra Speak 750", "code": "AZ-AUD-001", "cat": "Audio"},
            {"name": "Sony WH-1000XM5", "code": "AZ-AUD-002", "cat": "Audio"},
            # Accessories
            {
                "name": "Logitech MX Master 3S",
                "code": "AZ-ACC-001",
                "cat": "Accessories",
            },
            {"name": "Wacom Intuos Pro", "code": "AZ-ACC-002", "cat": "Accessories"},
        ]

        for i, a in enumerate(assets_to_seed):
            payload = {
                "name": a["name"],
                "aztec_code": a["code"],
                "category_id": cat_map[a["cat"]],
                "locker_id": all_locker_ids[i] if i < len(all_locker_ids) else None,
            }
            resp = await client.post("/assets", json=payload, headers=headers)
            if resp.status_code == 201:
                logger.info(f"  + Asset: {a['name']} ({a['code']})")

        # 6. Test Users
        logger.info("Seeding Test Users...")
        roles_resp = await client.get("/roles", headers=headers)
        user_role_id = next(
            (r["role_id"] for r in roles_resp.json() if r["role_name"] == "USER"), None
        )

        test_users = [
            {
                "first": "Jan",
                "last": "Janssens",
                "email": "jan.janssens@student.ucll.be",
                "nfc": "NFC-USER-001",
                "pin": "111111",
            },
            {
                "first": "Marie",
                "last": "Peeters",
                "email": "marie.peeters@student.ucll.be",
                "nfc": "NFC-USER-002",
                "pin": "222222",
            },
            {
                "first": "Tom",
                "last": "Wauters",
                "email": "tom.wauters@ucll.be",
                "nfc": "NFC-USER-003",
                "pin": "333333",
            },
            {
                "first": "Lotte",
                "last": "De Smet",
                "email": "lotte.desmet@student.ucll.be",
                "nfc": "NFC-USER-004",
                "pin": "444444",
            },
            {
                "first": "Sam",
                "last": "Vermeulen",
                "email": "sam.vermeulen@student.ucll.be",
                "nfc": "NFC-USER-005",
                "pin": "555555",
            },
        ]

        for u in test_users:
            payload = {
                "first_name": u["first"],
                "last_name": u["last"],
                "email": u["email"],
                "nfc_tag_id": u["nfc"],
                "pin": u["pin"],
                "role_id": user_role_id,
                "accepted_privacy_policy": True,
            }
            resp = await client.post("/users", json=payload, headers=headers)
            if resp.status_code == 201:
                logger.info(f"  + User: {u['first']} {u['last']}")

    logger.info("API Seeding successful.")


# ---------------------------------------------------------------------------
# Phase 3: Scenario Generation (Direct DB)
# ---------------------------------------------------------------------------


async def seed_scenarios():
    """
    Generates complex real-world scenarios by manipulating the database directly.
    """
    logger.info("--- Phase 3: Scenario Generation (Direct DB) ---")

    now = datetime.now(UTC)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Scenario: OVERDUE Loan
            # User Jan has an iPad that was due yesterday.
            jan_id = await get_user_id_by_email(session, "jan.janssens@student.ucll.be")
            ipad_id = await get_asset_id_by_code(session, "AZ-TAB-001")

            # Find a locker to 'checkout' from (even if it's now available)
            kiosk_res = await session.execute(select(Kiosk).limit(1))
            kiosk = kiosk_res.scalar_one()
            locker_res = await session.execute(
                select(Locker).filter_by(kiosk_id=kiosk.kiosk_id).limit(1)
            )
            locker = locker_res.scalar_one()

            overdue_loan = Loan(
                user_id=jan_id,
                asset_id=ipad_id,
                checkout_locker_id=locker.locker_id,
                loan_status=LoanStatus.OVERDUE,
                borrowed_at=now - timedelta(days=8),
                due_date=now - timedelta(days=1),
                reserved_at=now - timedelta(days=8, minutes=5),
            )
            session.add(overdue_loan)

            # Mark asset as BORROWED
            res = await session.execute(select(Asset).filter_by(asset_id=ipad_id))
            asset_ipad = res.scalar_one()
            asset_ipad.asset_status = AssetStatus.BORROWED
            asset_ipad.locker_id = None

            await log_audit_event(
                session,
                "LOAN_OVERDUE",
                {"loan_id": str(overdue_loan.loan_id)},
                user_id=jan_id,
            )
            logger.info("  + Scenario: Overdue loan created for Jan (iPad Pro).")

            # 2. Scenario: PENDING_INSPECTION (AI Detected Damage)
            # Marie returned a Dell XPS, but AI flagged a scratch.
            marie_id = await get_user_id_by_email(
                session, "marie.peeters@student.ucll.be"
            )
            dell_id = await get_asset_id_by_code(session, "AZ-LAP-001")

            # Find another locker for return
            locker2_res = await session.execute(
                select(Locker).filter_by(kiosk_id=kiosk.kiosk_id, logical_number=2)
            )
            locker2 = locker2_res.scalar_one()

            damage_loan = Loan(
                user_id=marie_id,
                asset_id=dell_id,
                checkout_locker_id=locker.locker_id,
                return_locker_id=locker2.locker_id,
                loan_status=LoanStatus.PENDING_INSPECTION,
                borrowed_at=now - timedelta(days=2),
                due_date=now + timedelta(days=5),
                returned_at=now - timedelta(hours=1),
            )
            session.add(damage_loan)

            # Asset & Locker state
            res = await session.execute(select(Asset).filter_by(asset_id=dell_id))
            asset_dell = res.scalar_one()
            asset_dell.asset_status = AssetStatus.PENDING_INSPECTION
            asset_dell.locker_id = locker2.locker_id
            locker2.locker_status = LockerStatus.MAINTENANCE

            # AI Evaluation
            eval_record = AIEvaluation(
                loan_id=damage_loan.loan_id,
                evaluation_type=EvaluationType.RETURN,
                photo_url="https://storage.easylend.be/evals/dell-scratch.jpg",
                ai_confidence=0.89,
                has_damage_detected=True,
                detected_objects={
                    "detections": [{"class": "laptop", "bbox": [10, 10, 100, 100]}]
                },
                model_version="yolo26-dual-model",
            )
            session.add(eval_record)
            await session.flush()

            # Damage Report
            report = DamageReport(
                evaluation_id=eval_record.evaluation_id,
                damage_type="Scratch",
                severity="Medium",
                segmentation_data={"polygon": [[10, 10], [20, 20], [10, 20]]},
                requires_repair=True,
            )
            session.add(report)

            await log_audit_event(
                session,
                "VISION_EVALUATION_PROCESSED",
                {"loan_id": str(damage_loan.loan_id), "damage": True},
            )
            logger.info(
                "  + Scenario: Quarantine case created for Marie (Dell XPS - Damage)."
            )

            # 3. Scenario: FRAUD_SUSPECTED
            # Tom tried to checkout a MacBook, but didn't take it.
            tom_id = await get_user_id_by_email(session, "tom.wauters@ucll.be")
            mac_id = await get_asset_id_by_code(session, "AZ-LAP-003")

            locker3_res = await session.execute(
                select(Locker).filter_by(kiosk_id=kiosk.kiosk_id, logical_number=3)
            )
            locker3 = locker3_res.scalar_one()

            fraud_loan = Loan(
                user_id=tom_id,
                asset_id=mac_id,
                checkout_locker_id=locker3.locker_id,
                loan_status=LoanStatus.FRAUD_SUSPECTED,
                reserved_at=now - timedelta(minutes=30),
            )
            session.add(fraud_loan)

            # Asset stays in locker
            res = await session.execute(select(Asset).filter_by(asset_id=mac_id))
            asset_mac = res.scalar_one()
            asset_mac.asset_status = AssetStatus.AVAILABLE
            asset_mac.locker_id = locker3.locker_id
            locker3.locker_status = LockerStatus.OCCUPIED

            # AI Evaluation confirming item still present during checkout analysis
            eval_fraud = AIEvaluation(
                loan_id=fraud_loan.loan_id,
                evaluation_type=EvaluationType.CHECKOUT,
                photo_url="https://storage.easylend.be/evals/macbook-not-taken.jpg",
                ai_confidence=0.95,
                has_damage_detected=False,
                detected_objects={
                    "detections": [{"class": "laptop", "bbox": [5, 5, 120, 120]}]
                },
                model_version="yolo26-dual-model",
            )
            session.add(eval_fraud)

            await log_audit_event(
                session,
                "LOAN_CHECKOUT_FRAUD",
                {"loan_id": str(fraud_loan.loan_id)},
                user_id=tom_id,
            )
            logger.info(
                "  + Scenario: Fraud suspected created for Tom (MacBook not taken)."
            )

            # 4. Scenario: DISPUTED (Grace Period Damage)
            # Lotte picked up a camera, but reported it broken within 5 mins.
            # We need a previous borrower (Sam) to be implicated.
            lotte_id = await get_user_id_by_email(
                session, "lotte.desmet@student.ucll.be"
            )
            sam_id = await get_user_id_by_email(
                session, "sam.vermeulen@student.ucll.be"
            )
            cam_id = await get_asset_id_by_code(session, "AZ-CAM-001")

            locker4_res = await session.execute(
                select(Locker).filter_by(kiosk_id=kiosk.kiosk_id, logical_number=4)
            )
            locker4 = locker4_res.scalar_one()

            # Past successful loan by Sam
            prev_loan = Loan(
                user_id=sam_id,
                asset_id=cam_id,
                checkout_locker_id=locker4.locker_id,
                return_locker_id=locker4.locker_id,
                loan_status=LoanStatus.COMPLETED,
                borrowed_at=now - timedelta(days=5),
                returned_at=now - timedelta(days=2),
            )
            session.add(prev_loan)

            # Current disputed loan by Lotte
            disputed_loan = Loan(
                user_id=lotte_id,
                asset_id=cam_id,
                checkout_locker_id=locker4.locker_id,
                loan_status=LoanStatus.DISPUTED,
                borrowed_at=now - timedelta(minutes=10),
                reserved_at=now - timedelta(minutes=15),
            )
            session.add(disputed_loan)

            # Suspend both users
            res_lotte = await session.execute(select(User).filter_by(user_id=lotte_id))
            user_lotte = res_lotte.scalar_one()
            user_lotte.locked_until = now + timedelta(days=7)

            res_sam = await session.execute(select(User).filter_by(user_id=sam_id))
            user_sam = res_sam.scalar_one()
            user_sam.locked_until = now + timedelta(days=7)

            # Asset & Locker
            res_cam = await session.execute(select(Asset).filter_by(asset_id=cam_id))
            asset_cam = res_cam.scalar_one()
            asset_cam.asset_status = AssetStatus.MAINTENANCE
            asset_cam.locker_id = locker4.locker_id
            locker4.locker_status = LockerStatus.MAINTENANCE

            await log_audit_event(
                session,
                "GRACE_PERIOD_DAMAGE_REPORTED",
                {
                    "loan_id": str(disputed_loan.loan_id),
                    "previous_loan_id": str(prev_loan.loan_id),
                },
                user_id=lotte_id,
            )
            logger.info(
                "  + Scenario: Disputed loan created for Lotte (Grace period report). Sam also suspended."
            )

            # 5. History: Some completed loans
            # Add some noise/history
            for i in range(5):
                hist_loan = Loan(
                    user_id=sam_id,
                    asset_id=dell_id,
                    checkout_locker_id=locker.locker_id,
                    return_locker_id=locker.locker_id,
                    loan_status=LoanStatus.COMPLETED,
                    borrowed_at=now - timedelta(days=20 + i),
                    returned_at=now - timedelta(days=18 + i),
                )
                session.add(hist_loan)

    logger.info("Scenario generation successful.")


# ---------------------------------------------------------------------------
# Main Entrypoint
# ---------------------------------------------------------------------------


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="EasyLend Development Seeder")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Purges the database before seeding (dev only).",
    )

    args = parser.parse_args()

    try:
        if args.reset:
            logger.info("Reset flag detected. Purging database...")
            success = await purge_database()
            if not success:
                logger.error("Purge failed. Aborting seed.")
                sys.exit(1)

        # First ensure foundation is set up
        await bootstrap_admin()
        # Then seed dev data
        await seed_master_data()
        await seed_scenarios()
        logger.info("Development seeding completed successfully.")
    except Exception:
        logger.exception("A critical error occurred during dev seeding")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

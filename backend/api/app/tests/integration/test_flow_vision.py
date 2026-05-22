import uuid

import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import (
    Asset,
    AssetStatus,
    Category,
    EvaluationType,
    Kiosk,
    Loan,
    LoanStatus,
    Locker,
    LockerStatus,
    Role,
    User,
    UserStatus,
)


@pytest.mark.asyncio
async def test_vision_checkout_confirmed(
    async_client: AsyncClient, integration_db_session: AsyncSession
):
    """
    Scenario: Vision Box uploads photo after checkout.
    Locker is EMPTY -> Loan becomes ACTIVE.
    """
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)
    user = User(
        user_id=uuid.uuid4(),
        role_id=role.role_id,
        first_name="V",
        last_name="T",
        email=f"v_{uuid.uuid4()}@e.com",
        pin_hash="x",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)
    kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="K", location_description="L")
    integration_db_session.add(kiosk)
    locker = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=301,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(locker)
    category = Category(category_id=uuid.uuid4(), category_name=f"C_{uuid.uuid4()}")
    integration_db_session.add(category)
    asset = Asset(
        asset_id=uuid.uuid4(),
        category_id=category.category_id,
        locker_id=locker.locker_id,
        name="A",
        aztec_code="A1",
        asset_status=AssetStatus.BORROWED,
    )
    integration_db_session.add(asset)
    loan = Loan(
        loan_id=uuid.uuid4(),
        user_id=user.user_id,
        asset_id=asset.asset_id,
        checkout_locker_id=locker.locker_id,
        loan_status=LoanStatus.RESERVED,
    )
    integration_db_session.add(loan)
    await integration_db_session.commit()

    with respx.mock:
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/detect").mock(
            return_value=Response(
                200, json={"locker_empty": True, "count": 0, "detections": []}
            )
        )
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/segment").mock(
            return_value=Response(
                200, json={"has_damage_detected": False, "detections": []}
            )
        )

        response = await async_client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data={
                "loan_id": str(loan.loan_id),
                "evaluation_type": EvaluationType.CHECKOUT,
            },
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 200
        await integration_db_session.refresh(loan)
        await integration_db_session.refresh(asset)
        await integration_db_session.refresh(locker)
        assert loan.loan_status == LoanStatus.ACTIVE
        assert asset.asset_status == AssetStatus.BORROWED
        assert asset.locker_id is None
        assert locker.locker_status == LockerStatus.AVAILABLE


@pytest.mark.asyncio
async def test_vision_return_confirmed(
    async_client: AsyncClient, integration_db_session: AsyncSession
):
    """
    Scenario: Vision Box uploads photo after return.
    Locker is NOT EMPTY & NO DAMAGE -> Loan becomes COMPLETED.
    """
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)
    user = User(
        user_id=uuid.uuid4(),
        role_id=role.role_id,
        first_name="V",
        last_name="R",
        email=f"vr_{uuid.uuid4()}@e.com",
        pin_hash="x",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)
    kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="K", location_description="L")
    integration_db_session.add(kiosk)

    # We need TWO lockers: one for historical checkout, one for current return
    locker_checkout = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=400,
        locker_status=LockerStatus.AVAILABLE,
    )
    locker_return = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=401,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(locker_checkout)
    integration_db_session.add(locker_return)

    category = Category(category_id=uuid.uuid4(), category_name=f"C_{uuid.uuid4()}")
    integration_db_session.add(category)
    asset = Asset(
        asset_id=uuid.uuid4(),
        category_id=category.category_id,
        locker_id=None,
        name="A",
        aztec_code="A2",
        asset_status=AssetStatus.BORROWED,
    )
    integration_db_session.add(asset)

    loan = Loan(
        loan_id=uuid.uuid4(),
        user_id=user.user_id,
        asset_id=asset.asset_id,
        checkout_locker_id=locker_checkout.locker_id,
        return_locker_id=locker_return.locker_id,
        loan_status=LoanStatus.RETURNING,
    )
    integration_db_session.add(loan)
    await integration_db_session.commit()

    with respx.mock:
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/detect").mock(
            return_value=Response(
                200, json={"locker_empty": False, "count": 1, "detections": []}
            )
        )
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/segment").mock(
            return_value=Response(
                200, json={"has_damage_detected": False, "detections": []}
            )
        )

        response = await async_client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data={
                "loan_id": str(loan.loan_id),
                "evaluation_type": EvaluationType.RETURN,
            },
            files={"file": ("return.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 200
        await integration_db_session.refresh(loan)
        await integration_db_session.refresh(asset)
        await integration_db_session.refresh(locker_return)
        assert loan.loan_status == LoanStatus.COMPLETED
        assert asset.asset_status == AssetStatus.AVAILABLE
        assert asset.locker_id == locker_return.locker_id
        assert locker_return.locker_status == LockerStatus.OCCUPIED


@pytest.mark.asyncio
async def test_vision_checkout_fraud_locker_not_empty(
    async_client: AsyncClient, integration_db_session: AsyncSession
):
    """
    Scenario: Checkout evaluation finds locker is NOT empty (user didn't take the item).
    Expect Loan -> FRAUD_SUSPECTED.
    """
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)
    user = User(
        user_id=uuid.uuid4(),
        role_id=role.role_id,
        first_name="F",
        last_name="T",
        email=f"f_{uuid.uuid4()}@e.com",
        pin_hash="x",
    )
    integration_db_session.add(user)
    kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="K", location_description="L")
    integration_db_session.add(kiosk)
    locker = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=501,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(locker)
    category = Category(category_id=uuid.uuid4(), category_name=f"C_{uuid.uuid4()}")
    integration_db_session.add(category)
    asset = Asset(
        asset_id=uuid.uuid4(),
        category_id=category.category_id,
        locker_id=locker.locker_id,
        name="A",
        aztec_code="A3",
        asset_status=AssetStatus.BORROWED,
    )
    integration_db_session.add(asset)
    loan = Loan(
        loan_id=uuid.uuid4(),
        user_id=user.user_id,
        asset_id=asset.asset_id,
        checkout_locker_id=locker.locker_id,
        loan_status=LoanStatus.RESERVED,
    )
    integration_db_session.add(loan)
    await integration_db_session.commit()

    with respx.mock:
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/detect").mock(
            return_value=Response(
                200, json={"locker_empty": False, "count": 1, "detections": []}
            )
        )
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/segment").mock(
            return_value=Response(
                200, json={"has_damage_detected": False, "detections": []}
            )
        )

        response = await async_client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data={
                "loan_id": str(loan.loan_id),
                "evaluation_type": EvaluationType.CHECKOUT,
            },
            files={"file": ("f.jpg", b"b", "image/jpeg")},
        )
        assert response.status_code == 200
        await integration_db_session.refresh(loan)
        assert loan.loan_status == LoanStatus.FRAUD_SUSPECTED


@pytest.mark.asyncio
async def test_vision_return_damage_pending_inspection(
    async_client: AsyncClient, integration_db_session: AsyncSession
):
    """
    Scenario: Return evaluation finds damage.
    Expect Loan -> PENDING_INSPECTION.
    """
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)
    user = User(
        user_id=uuid.uuid4(),
        role_id=role.role_id,
        first_name="D",
        last_name="T",
        email=f"d_{uuid.uuid4()}@e.com",
        pin_hash="x",
    )
    integration_db_session.add(user)
    kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="K", location_description="L")
    integration_db_session.add(kiosk)
    locker_checkout = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=600,
        locker_status=LockerStatus.AVAILABLE,
    )
    locker_return = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=601,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(locker_checkout)
    integration_db_session.add(locker_return)
    category = Category(category_id=uuid.uuid4(), category_name=f"C_{uuid.uuid4()}")
    integration_db_session.add(category)
    asset = Asset(
        asset_id=uuid.uuid4(),
        category_id=category.category_id,
        locker_id=None,
        name="A",
        aztec_code="A4",
        asset_status=AssetStatus.BORROWED,
    )
    integration_db_session.add(asset)
    loan = Loan(
        loan_id=uuid.uuid4(),
        user_id=user.user_id,
        asset_id=asset.asset_id,
        checkout_locker_id=locker_checkout.locker_id,
        return_locker_id=locker_return.locker_id,
        loan_status=LoanStatus.RETURNING,
    )
    integration_db_session.add(loan)
    await integration_db_session.commit()

    with respx.mock:
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/detect").mock(
            return_value=Response(
                200, json={"locker_empty": False, "count": 1, "detections": []}
            )
        )
        respx.post(f"{settings.VISION_SERVICE_URL.rstrip('/')}/segment").mock(
            return_value=Response(
                200, json={"has_damage_detected": True, "detections": []}
            )
        )

        response = await async_client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data={
                "loan_id": str(loan.loan_id),
                "evaluation_type": EvaluationType.RETURN,
            },
            files={"file": ("d.jpg", b"b", "image/jpeg")},
        )
        assert response.status_code == 200
        await integration_db_session.refresh(loan)
        assert loan.loan_status == LoanStatus.PENDING_INSPECTION

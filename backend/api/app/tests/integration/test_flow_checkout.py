import uuid

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models import (
    Asset,
    AssetStatus,
    Category,
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
async def test_checkout_hardware_offline_fallback(
    async_client: AsyncClient,
    integration_db_session: AsyncSession,
    integration_redis_client: Redis,
):
    """
    Scenario: User initiates checkout via Aztec code.
    DB succeeds, but hardware command fails (simulated here by lack of real WS connection).
    Expect 207 Multi-Status and RESERVED status.
    """

    # 1. Seed data
    # Role - Ensure unique name
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)

    # User
    user_id = uuid.uuid4()
    user = User(
        user_id=user_id,
        role_id=role.role_id,
        first_name="Integration",
        last_name="Tester",
        email="test@easylend.com",
        pin_hash="fake_hash",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)

    # Kiosk
    kiosk_id = uuid.uuid4()
    kiosk = Kiosk(
        kiosk_id=kiosk_id,
        name="Integration Kiosk",
        location_description="Lab",
        kiosk_status="ONLINE",
    )
    integration_db_session.add(kiosk)

    # Locker - Start as AVAILABLE for checkout
    locker_id = uuid.uuid4()
    locker = Locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=101,
        locker_status=LockerStatus.AVAILABLE,
    )
    integration_db_session.add(locker)

    # Category
    category = Category(
        category_id=uuid.uuid4(), category_name=f"Category_{uuid.uuid4()}"
    )
    integration_db_session.add(category)

    # Asset
    asset_id = uuid.uuid4()
    asset = Asset(
        asset_id=asset_id,
        category_id=category.category_id,
        locker_id=locker_id,
        name="iPad Pro",
        aztec_code="INT-CHECKOUT-001",
        asset_status=AssetStatus.AVAILABLE,
    )
    integration_db_session.add(asset)

    await integration_db_session.commit()

    # 2. Mock kiosk presence in Redis
    await integration_redis_client.set(f"kiosk:presence:{kiosk_id}", "online")

    # 3. Generate JWT
    token = create_access_token(user_id, "member")

    # 4. Request checkout
    response = await async_client.post(
        "/api/v1/loans/checkout",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"aztec_code": "INT-CHECKOUT-001"},
    )

    # 5. Assertions
    assert response.status_code == 207
    data = response.json()
    assert data["loan_status"] == LoanStatus.RESERVED

    # Verify DB state
    asset_db = (
        await integration_db_session.execute(
            select(Asset).where(Asset.asset_id == asset_id)
        )
    ).scalar_one()

    locker_db = (
        await integration_db_session.execute(
            select(Locker).where(Locker.locker_id == locker_id)
        )
    ).scalar_one()

    loan_db = (
        await integration_db_session.execute(
            select(Loan).where(Loan.asset_id == asset_id)
        )
    ).scalar_one()

    assert asset_db.asset_status == AssetStatus.BORROWED
    # Per State Machine: (None, RESERVED) leaves locker status unchanged (unless specified)
    # Actually, LoanStateMachine.apply_transition says:
    # (None, LoanStatus.RESERVED): asset_status=AssetStatus.BORROWED, locker_status remains unchanged or is None
    # Let's check what happened in previous run. It failed because it expected OCCUPIED but got AVAILABLE.
    # If we seed as AVAILABLE and transition to RESERVED, locker stays AVAILABLE until pickup (ACTIVE).
    assert locker_db.locker_status == LockerStatus.AVAILABLE
    assert loan_db.loan_status == LoanStatus.RESERVED

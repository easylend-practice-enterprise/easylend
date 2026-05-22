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

    # Locker - Seed as OCCUPIED as it contains the asset
    locker_id = uuid.uuid4()
    locker = Locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=101,
        locker_status=LockerStatus.OCCUPIED,
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
    # HTTP 207 Multi-Status is returned if DB succeeds but HW fails immediately
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
    # Per State Machine: (None, RESERVED) leaves locker status unchanged.
    # Since we seeded as OCCUPIED, it must remain OCCUPIED until the user picks up the item (ACTIVE).
    assert locker_db.locker_status == LockerStatus.OCCUPIED
    assert loan_db.loan_status == LoanStatus.RESERVED


@pytest.mark.asyncio
async def test_checkout_blocked_by_overdue_loan(
    async_client: AsyncClient,
    integration_db_session: AsyncSession,
    integration_redis_client: Redis,
):
    """
    Scenario: User has one OVERDUE loan. They try to checkout a second item.
    Expect 403 Forbidden.
    """
    # 1. Seed User
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)
    user = User(
        user_id=uuid.uuid4(),
        role_id=role.role_id,
        first_name="Overdue",
        last_name="User",
        email="overdue@test.com",
        pin_hash="x",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)

    # 2. Seed Overdue Loan
    asset_overdue = Asset(
        asset_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        name="Late Item",
        aztec_code="LATE-001",
        asset_status=AssetStatus.BORROWED,
    )
    # Asset category must exist
    cat = Category(category_id=asset_overdue.category_id, category_name="Cat1")
    integration_db_session.add(cat)
    integration_db_session.add(asset_overdue)

    # Historical Locker for the overdue loan
    hist_kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="HK", location_description="HL")
    integration_db_session.add(hist_kiosk)
    hist_locker = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=hist_kiosk.kiosk_id,
        logical_number=999,
        locker_status=LockerStatus.AVAILABLE,
    )
    integration_db_session.add(hist_locker)

    loan_overdue = Loan(
        loan_id=uuid.uuid4(),
        user_id=user.user_id,
        asset_id=asset_overdue.asset_id,
        checkout_locker_id=hist_locker.locker_id,
        loan_status=LoanStatus.OVERDUE,
    )
    integration_db_session.add(loan_overdue)

    # 3. Seed Target Item for new checkout
    target_kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="K", location_description="L")
    integration_db_session.add(target_kiosk)
    target_locker = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=target_kiosk.kiosk_id,
        logical_number=201,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(target_locker)
    target_asset = Asset(
        asset_id=uuid.uuid4(),
        category_id=cat.category_id,
        locker_id=target_locker.locker_id,
        name="Target Item",
        aztec_code="TARGET-001",
        asset_status=AssetStatus.AVAILABLE,
    )
    integration_db_session.add(target_asset)

    await integration_db_session.commit()
    await integration_redis_client.set(
        f"kiosk:presence:{target_kiosk.kiosk_id}", "online"
    )

    # 4. Attempt Checkout
    token = create_access_token(user.user_id, "member")
    response = await async_client.post(
        "/api/v1/loans/checkout",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-overdue"},
        json={"aztec_code": "TARGET-001"},
    )

    # 5. Assert 403
    assert response.status_code == 403
    assert "overdue items" in response.json()["detail"]


@pytest.mark.asyncio
async def test_checkout_blocked_by_quota_limit(
    async_client: AsyncClient,
    integration_db_session: AsyncSession,
    integration_redis_client: Redis,
):
    """
    Scenario: User has 2 ACTIVE loans. They try to checkout a 3rd item.
    Expect 403 Forbidden.
    """
    # 1. Seed User
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)
    user = User(
        user_id=uuid.uuid4(),
        role_id=role.role_id,
        first_name="Quota",
        last_name="User",
        email="quota@test.com",
        pin_hash="x",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)
    cat = Category(category_id=uuid.uuid4(), category_name="CatQ")
    integration_db_session.add(cat)

    # 2. Seed 2 Active Loans
    kiosk_q = Kiosk(kiosk_id=uuid.uuid4(), name="QK", location_description="QL")
    integration_db_session.add(kiosk_q)

    for i in range(2):
        locker = Locker(
            locker_id=uuid.uuid4(),
            kiosk_id=kiosk_q.kiosk_id,
            logical_number=900 + i,
            locker_status=LockerStatus.AVAILABLE,
        )
        integration_db_session.add(locker)

        asset = Asset(
            asset_id=uuid.uuid4(),
            category_id=cat.category_id,
            name=f"Item {i}",
            aztec_code=f"BUSY-{i}",
            asset_status=AssetStatus.BORROWED,
        )
        integration_db_session.add(asset)
        loan = Loan(
            loan_id=uuid.uuid4(),
            user_id=user.user_id,
            asset_id=asset.asset_id,
            checkout_locker_id=locker.locker_id,
            loan_status=LoanStatus.ACTIVE,
        )
        integration_db_session.add(loan)

    # 3. Seed 3rd Item
    kiosk = Kiosk(kiosk_id=uuid.uuid4(), name="K", location_description="L")
    integration_db_session.add(kiosk)
    locker = Locker(
        locker_id=uuid.uuid4(),
        kiosk_id=kiosk.kiosk_id,
        logical_number=301,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(locker)
    asset_3 = Asset(
        asset_id=uuid.uuid4(),
        category_id=cat.category_id,
        locker_id=locker.locker_id,
        name="Item 3",
        aztec_code="TARGET-Q",
        asset_status=AssetStatus.AVAILABLE,
    )
    integration_db_session.add(asset_3)

    await integration_db_session.commit()
    await integration_redis_client.set(f"kiosk:presence:{kiosk.kiosk_id}", "online")

    # 4. Attempt 3rd Checkout
    token = create_access_token(user.user_id, "member")
    response = await async_client.post(
        "/api/v1/loans/checkout",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-quota"},
        json={"aztec_code": "TARGET-Q"},
    )

    # 5. Assert 403
    assert response.status_code == 403
    assert "Maximum of" in response.json()["detail"]

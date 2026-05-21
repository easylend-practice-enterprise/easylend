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
async def test_return_no_available_lockers_returns_503(
    async_client: AsyncClient,
    integration_db_session: AsyncSession,
    integration_redis_client: Redis,
):
    """
    Scenario: User tries to return an asset at a kiosk with no available lockers.
    Expect 503 Service Unavailable and Loan stays ACTIVE.
    """
    # 1. Seed data
    # Unique Role
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)

    user_id = uuid.uuid4()
    user = User(
        user_id=user_id,
        role_id=role.role_id,
        first_name="Return",
        last_name="Tester",
        email="return@easylend.com",
        pin_hash="fake_hash",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)

    kiosk_id = uuid.uuid4()
    kiosk = Kiosk(
        kiosk_id=kiosk_id,
        name="Full Kiosk",
        location_description="Full Lab",
        kiosk_status="ONLINE",
    )
    integration_db_session.add(kiosk)

    # Occupied Locker for checkout
    checkout_locker_id = uuid.uuid4()
    checkout_locker = Locker(
        locker_id=checkout_locker_id,
        kiosk_id=kiosk_id,
        logical_number=100,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(checkout_locker)

    # 2 Occupied Lockers at return kiosk
    for i in range(2):
        locker = Locker(
            locker_id=uuid.uuid4(),
            kiosk_id=kiosk_id,
            logical_number=i,
            locker_status=LockerStatus.OCCUPIED,
        )
        integration_db_session.add(locker)

    category = Category(
        category_id=uuid.uuid4(), category_name=f"Return Category 1_{uuid.uuid4()}"
    )
    integration_db_session.add(category)

    asset_id = uuid.uuid4()
    aztec_code = "RETURN-FULL-001"
    asset = Asset(
        asset_id=asset_id,
        category_id=category.category_id,
        name="MacBook Air",
        aztec_code=aztec_code,
        asset_status=AssetStatus.BORROWED,
    )
    integration_db_session.add(asset)

    loan = Loan(
        loan_id=uuid.uuid4(),
        user_id=user_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
        loan_status=LoanStatus.ACTIVE,
    )
    integration_db_session.add(loan)

    await integration_db_session.commit()

    # 2. Mock kiosk presence
    await integration_redis_client.set(f"kiosk:presence:{kiosk_id}", "online")

    # 3. Request return
    token = create_access_token(user_id, "member")
    response = await async_client.post(
        "/api/v1/loans/return/initiate",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"aztec_code": aztec_code, "kiosk_id": str(kiosk_id)},
    )

    # 4. Assertions
    assert response.status_code == 503

    # Verify loan is still ACTIVE
    loan_db = (
        await integration_db_session.execute(
            select(Loan).where(Loan.asset_id == asset_id)
        )
    ).scalar_one()
    assert loan_db.loan_status == LoanStatus.ACTIVE


@pytest.mark.asyncio
async def test_return_hardware_offline_fallback(
    async_client: AsyncClient,
    integration_db_session: AsyncSession,
    integration_redis_client: Redis,
):
    """
    Scenario: User initiates return. DB updates successfully, but hardware command fails.
    Expect 207 Multi-Status, Loan becomes RETURNING, Locker becomes OCCUPIED.
    """
    # 1. Seed data
    # Unique Role
    role = Role(role_id=uuid.uuid4(), role_name=f"member_{uuid.uuid4()}")
    integration_db_session.add(role)

    user_id = uuid.uuid4()
    user = User(
        user_id=user_id,
        role_id=role.role_id,
        first_name="Return",
        last_name="Fallback",
        email="fallback@easylend.com",
        pin_hash="fake_hash",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(user)

    kiosk_id = uuid.uuid4()
    kiosk = Kiosk(
        kiosk_id=kiosk_id,
        name="Available Kiosk",
        location_description="Lab",
        kiosk_status="ONLINE",
    )
    integration_db_session.add(kiosk)

    # Locker for checkout
    checkout_locker_id = uuid.uuid4()
    checkout_locker = Locker(
        locker_id=checkout_locker_id,
        kiosk_id=kiosk_id,
        logical_number=201,
        locker_status=LockerStatus.OCCUPIED,
    )
    integration_db_session.add(checkout_locker)

    # One available locker for return
    locker_id = uuid.uuid4()
    locker = Locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=202,
        locker_status=LockerStatus.AVAILABLE,
    )
    integration_db_session.add(locker)

    category = Category(
        category_id=uuid.uuid4(), category_name=f"Return Category 2_{uuid.uuid4()}"
    )
    integration_db_session.add(category)

    asset_id = uuid.uuid4()
    aztec_code = "RETURN-OK-001"
    asset = Asset(
        asset_id=asset_id,
        category_id=category.category_id,
        name="MacBook Pro",
        aztec_code=aztec_code,
        asset_status=AssetStatus.BORROWED,
    )
    integration_db_session.add(asset)

    loan_id = uuid.uuid4()
    loan = Loan(
        loan_id=loan_id,
        user_id=user_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
        loan_status=LoanStatus.ACTIVE,
    )
    integration_db_session.add(loan)

    await integration_db_session.commit()

    # 2. Mock kiosk presence
    await integration_redis_client.set(f"kiosk:presence:{kiosk_id}", "online")

    # 3. Request return
    token = create_access_token(user_id, "member")
    response = await async_client.post(
        "/api/v1/loans/return/initiate",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"aztec_code": aztec_code, "kiosk_id": str(kiosk_id)},
    )

    # 4. Assertions
    # 207 Multi-Status expected when DB succeeds but hardware command fails immediately
    assert response.status_code == 207
    data = response.json()
    assert data["loan_status"] == LoanStatus.RETURNING

    # Verify DB state
    loan_db = (
        await integration_db_session.execute(
            select(Loan).where(Loan.loan_id == loan_id)
        )
    ).scalar_one()

    locker_db = (
        await integration_db_session.execute(
            select(Locker).where(Locker.locker_id == locker_id)
        )
    ).scalar_one()

    assert loan_db.loan_status == LoanStatus.RETURNING
    assert loan_db.return_locker_id == locker_id
    assert locker_db.locker_status == LockerStatus.OCCUPIED

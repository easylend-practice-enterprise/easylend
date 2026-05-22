import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Role, User, UserStatus


@pytest.mark.asyncio
async def test_audit_chain_batch_verification_continuity(
    async_client: AsyncClient, integration_db_session: AsyncSession
):
    """
    Scenario: Verify the Cryptographic Audit Trail across multiple batches.
    1. Create 5 audit records manually (to bypass orchestration for speed).
    2. Call /audit/verify with limit=2 to verify batches.
    3. Ensure continuity fix (offset skip-1) works as documented.
    """
    # 1. Setup Admin User
    role_admin = Role(role_id=uuid.uuid4(), role_name="ADMIN")
    integration_db_session.add(role_admin)
    admin = User(
        user_id=uuid.uuid4(),
        role_id=role_admin.role_id,
        first_name="Admin",
        last_name="Audit",
        email="admin-audit@test.com",
        pin_hash="x",
        status=UserStatus.ACTIVE,
    )
    integration_db_session.add(admin)
    await integration_db_session.commit()

    # 2. Generate 5 linked Audit Records
    # Using the core hashing logic would be best, but we want to test the endpoint's traversal logic
    from app.core.audit import log_audit_event

    # We must use the real log_audit_event to get valid hashes
    for i in range(5):
        await log_audit_event(
            integration_db_session,
            action_type=f"TEST_EVENT_{i}",
            payload={"index": i},
            user_id=admin.user_id,
        )
    await integration_db_session.commit()

    # 3. Verify Batch 1 (Records 0, 1)
    from app.core.security import create_access_token

    token = create_access_token(admin.user_id, "ADMIN")

    response_1 = await async_client.get(
        "/api/v1/audit/verify?skip=0&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_1.status_code == 200
    assert response_1.json()["is_valid"] is True

    # 4. Verify Batch 2 (Records 2, 3) - This tests the continuity fix
    response_2 = await async_client.get(
        "/api/v1/audit/verify?skip=2&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_2.status_code == 200
    assert response_2.json()["is_valid"] is True

    # 5. Verify Batch 3 (Record 4)
    response_3 = await async_client.get(
        "/api/v1/audit/verify?skip=4&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_3.status_code == 200
    assert response_3.json()["is_valid"] is True

    # 6. Simulate Tampering
    # Directly modify record 2 (middle of the chain)
    import sqlalchemy as sa

    result = await integration_db_session.execute(
        sa.select(AuditLog).offset(2).limit(1)
    )
    target_log = result.scalar_one()
    target_log.payload = {"tampered": "data"}
    await integration_db_session.commit()

    # 7. Re-verify Batch 2 - Should fail
    response_fail = await async_client.get(
        "/api/v1/audit/verify?skip=2&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_fail.status_code == 200
    assert response_fail.json()["is_valid"] is False
    assert response_fail.json()["tampered_record_id"] == str(target_log.audit_id)

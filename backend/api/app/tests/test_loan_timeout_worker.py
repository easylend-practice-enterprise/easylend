import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.db.models import AssetStatus, LoanStatus, LockerStatus
from app.tests.conftest import _QueuedSession
from app.workers.loan_timeout_worker import process_reserved_loan_timeouts


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id", uuid.uuid4()),
        loan_status=kwargs.get("loan_status", "RESERVED"),
        reserved_at=kwargs.get("reserved_at"),
    )


def _make_locker(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        locker_status=kwargs.get("locker_status", "AVAILABLE"),
    )


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        asset_status=kwargs.get("asset_status", "BORROWED"),
        locker_id=kwargs.get("locker_id"),
    )


@pytest.mark.anyio
async def test_process_reserved_loan_timeouts_updates_loan_locker_and_audit():
    now = datetime.now(UTC)
    locker_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    loan = _make_loan(
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
        reserved_at=now - timedelta(minutes=5),
    )
    locker = _make_locker(locker_id=locker_id, locker_status="AVAILABLE")
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")

    # Execute order in process_reserved_loan_timeouts:
    # [1] query timed-out reserved loans
    # [2] query asset
    # [3] query checkout locker
    # [4] query most recent audit log (inside log_audit_event)
    fake_db = _QueuedSession([loan], asset, locker, None)

    processed_count = await process_reserved_loan_timeouts(fake_db, now=now)

    assert processed_count == 1
    assert loan.loan_status == LoanStatus.PENDING_INSPECTION
    assert locker.locker_status == LockerStatus.MAINTENANCE
    assert asset.asset_status == AssetStatus.PENDING_INSPECTION
    assert asset.locker_id == locker_id
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1

    audit_log = fake_db.added[0]
    assert audit_log.action_type == "LOAN_RESERVED_TIMEOUT"
    assert audit_log.payload["event"] == "reserved_loan_timeout"
    assert audit_log.payload["loan_id"] == str(loan.loan_id)
    assert audit_log.payload["locker_id"] == str(locker.locker_id)
    assert len(audit_log.previous_hash) == 64
    assert len(audit_log.current_hash) == 64


@pytest.mark.anyio
async def test_process_reserved_loan_timeouts_no_matches_does_nothing():
    fake_db = _QueuedSession([])

    processed_count = await process_reserved_loan_timeouts(fake_db)

    assert processed_count == 0
    assert fake_db.commit_calls == 0
    assert len(fake_db.added) == 0

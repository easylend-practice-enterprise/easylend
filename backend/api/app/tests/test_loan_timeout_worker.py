"""
Tests for the reserved-loan timeout worker (app/workers/loan_timeout_worker.py).
"""

import importlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import AssetStatus, LoanStatus, LockerStatus


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id"),
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResult:
    """Mirrors _FakeResult from conftest."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value] if self._value is not None else []


class _FakeSession:
    """Fake async session supporting ``async with AsyncSessionLocal() as db``."""

    def __init__(self, *execute_results) -> None:
        self._queue = list(execute_results)
        self.added: list = []
        self.commit_calls: int = 0
        self.rollback_calls: int = 0

    async def execute(self, _query):  # noqa: ARG002
        value = self._queue.pop(0) if self._queue else None
        return _FakeResult(value)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def flush(self):
        return None

    async def refresh(self, obj):
        if hasattr(obj, "loan_id") and getattr(obj, "loan_id") is None:
            setattr(obj, "loan_id", uuid.uuid4())

    def add(self, obj):
        self.added.append(obj)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _reload_with_fake_session(fake_session_factory):
    """
    Reload app.workers.loan_timeout_worker with a patched AsyncSessionLocal.

    Patch AsyncSessionLocal at its SOURCE (app.db.database) so that when reload()
    re-executes the worker module, its "from app.db.database import
    AsyncSessionLocal" picks up the fake.
    """
    import app.db.database as db_mod
    import app.workers.loan_timeout_worker as mod

    with patch.object(db_mod, "AsyncSessionLocal", fake_session_factory):
        importlib.reload(mod)

    return mod, mod._process_single_reserved_loan, mod.process_reserved_loan_timeouts


# ---------------------------------------------------------------------------
# _process_single_reserved_loan
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_process_single_reserved_loan_marks_inspection_and_creates_audit():
    """A timed-out RESERVED loan is moved to PENDING_INSPECTION with audit log."""
    now = datetime.now(UTC)
    locker_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    loan = _make_loan(
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status=LoanStatus.RESERVED,
        reserved_at=now - timedelta(minutes=5),
    )
    locker = _make_locker(locker_id=locker_id, locker_status=LockerStatus.AVAILABLE)
    asset = _make_asset(
        asset_id=asset_id, asset_status=AssetStatus.BORROWED, locker_id=locker_id
    )
    # Execute call sequence in _process_single_reserved_loan:
    # [1] SELECT Loan FOR UPDATE NOWAIT
    # [2] SELECT Asset FOR UPDATE NOWAIT
    # [3] SELECT Locker FOR UPDATE NOWAIT
    # [4] log_audit_event: SELECT most recent audit log
    fake_db = _FakeSession(loan, asset, locker, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(loan.loan_id, now, timeout_minutes=3)

    assert result is True
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
async def test_process_single_reserved_loan_skips_if_loan_not_found():
    """If the loan row does not exist, returns False without side effects."""
    now = datetime.now(UTC)
    fake_db = _FakeSession(None, None, None, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(uuid.uuid4(), now, 3)

    assert result is False
    assert fake_db.commit_calls == 0


@pytest.mark.anyio
async def test_process_single_reserved_loan_skips_if_already_active():
    """If the loan is no longer RESERVED, it is skipped."""
    now = datetime.now(UTC)
    loan = _make_loan(
        loan_status=LoanStatus.ACTIVE,
        reserved_at=now - timedelta(minutes=5),
    )
    fake_db = _FakeSession(loan, None, None, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(loan.loan_id, now, 3)

    assert result is False
    assert fake_db.commit_calls == 0


@pytest.mark.anyio
async def test_process_single_reserved_loan_skips_if_not_yet_timed_out():
    """If reserved_at is still within the timeout window, the loan is not processed."""
    now = datetime.now(UTC)
    loan = _make_loan(
        loan_status=LoanStatus.RESERVED,
        reserved_at=now - timedelta(minutes=1),  # within 3-minute window
    )
    fake_db = _FakeSession(loan, None, None, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(loan.loan_id, now, 3)

    assert result is False
    assert fake_db.commit_calls == 0


# ---------------------------------------------------------------------------
# process_reserved_loan_timeouts (batch dispatcher)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_process_reserved_loan_timeouts_returns_zero_when_batch_is_empty():
    """If no timed-out loans exist, zero is returned."""
    fake_db = _FakeSession([])

    _, _, _proc = _reload_with_fake_session(lambda: fake_db)
    processed = await _proc()

    assert processed == 0


@pytest.mark.anyio
async def test_process_reserved_loan_timeouts_calls_process_for_each_batch_id():
    """
    process_reserved_loan_timeouts dispatches one call to _process_single_reserved_loan
    per loan ID. Uses AsyncMock to count internal calls.
    """
    now = datetime.now(UTC)
    loan_a = _make_loan(
        loan_status=LoanStatus.RESERVED,
        reserved_at=now - timedelta(minutes=5),
    )
    loan_b = _make_loan(
        loan_status=LoanStatus.RESERVED,
        reserved_at=now - timedelta(minutes=6),
    )

    call_count = [0]

    def factory():
        call_count[0] += 1
        if call_count[0] == 1:
            return _FakeSession([loan_a.loan_id, loan_b.loan_id])
        return _FakeSession(None, None, None, None)

    _, _, _proc = _reload_with_fake_session(factory)

    import app.workers.loan_timeout_worker as mod

    mock_proc = AsyncMock(return_value=True)
    with patch.object(mod, "_process_single_reserved_loan", mock_proc):
        processed = await _proc(now=now, timeout_minutes=3)

    assert processed == 2
    assert mock_proc.call_count == 2

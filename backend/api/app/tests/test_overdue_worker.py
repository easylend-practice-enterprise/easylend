"""
Tests for the overdue worker (app/workers/overdue_worker.py).

The overdue worker module is imported by conftest at pytest startup, so its
AsyncSessionLocal reference is already bound to the real sessionmaker.
For tests that need a fake session (e.g. _process_single_loan), we use
importlib.reload() inside a patch context that patches AsyncSessionLocal at its
SOURCE (app.db.database) so the reload picks up the fake.
"""

import importlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import LoanStatus


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        user_id=kwargs.get("user_id", uuid.uuid4()),
        loan_status=kwargs.get("loan_status", LoanStatus.ACTIVE),
        due_date=kwargs.get("due_date"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResult:
    """Mirrors _FakeResult from conftest — unified result stub."""

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
    """
    Fake async session that supports ``async with AsyncSessionLocal() as db``.
    """

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
    Reload app.workers.overdue_worker with a patched AsyncSessionLocal.

    The overdue worker is imported at pytest startup (via conftest importing it).
    We patch AsyncSessionLocal at its SOURCE (app.db.database) so that when
    reload() re-executes the overdue worker module, its
    "from app.db.database import AsyncSessionLocal" picks up the fake.
    """
    import app.db.database as db_mod
    import app.workers.overdue_worker as mod

    with patch.object(db_mod, "AsyncSessionLocal", fake_session_factory):
        importlib.reload(mod)

    return mod, mod._process_single_loan, mod.process_overdue_loans


# ---------------------------------------------------------------------------
# _process_single_loan
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_process_single_loan_marks_overdue_and_creates_audit():
    """A loan that is overdue and ACTIVE is marked OVERDUE with an audit event."""
    now = datetime.now(UTC)
    loan = _make_loan(
        loan_status=LoanStatus.ACTIVE,
        due_date=now - timedelta(hours=1),
    )
    fake_db = _FakeSession(loan, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(loan.loan_id, now)

    assert result is True
    assert loan.loan_status == LoanStatus.OVERDUE
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1

    audit_log = fake_db.added[0]
    assert audit_log.action_type == "LOAN_OVERDUE"
    assert audit_log.payload["loan_id"] == str(loan.loan_id)
    assert audit_log.payload["asset_id"] == str(loan.asset_id)
    assert len(audit_log.previous_hash) == 64
    assert len(audit_log.current_hash) == 64


@pytest.mark.anyio
async def test_process_single_loan_skips_if_loan_not_found():
    """If the loan ID does not exist, _process_single_loan returns False gracefully."""
    now = datetime.now(UTC)
    fake_db = _FakeSession(None, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(uuid.uuid4(), now)

    assert result is False
    assert fake_db.commit_calls == 0


@pytest.mark.anyio
async def test_process_single_loan_skips_if_already_overdue():
    """If the loan is no longer ACTIVE (e.g. already returned), it is skipped."""
    now = datetime.now(UTC)
    loan = _make_loan(
        loan_status=LoanStatus.OVERDUE,
        due_date=now - timedelta(hours=1),
    )
    fake_db = _FakeSession(loan, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(loan.loan_id, now)

    assert result is False
    assert fake_db.commit_calls == 0


@pytest.mark.anyio
async def test_process_single_loan_skips_if_not_yet_overdue():
    """If due_date is still in the future, the loan is not processed."""
    now = datetime.now(UTC)
    loan = _make_loan(
        loan_status=LoanStatus.ACTIVE,
        due_date=now + timedelta(hours=1),
    )
    fake_db = _FakeSession(loan, None)

    _, _proc, _ = _reload_with_fake_session(lambda: fake_db)
    result = await _proc(loan.loan_id, now)

    assert result is False
    assert fake_db.commit_calls == 0


# ---------------------------------------------------------------------------
# process_overdue_loans (batch dispatcher)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_process_overdue_loans_returns_zero_when_batch_is_empty():
    """If the batch query returns no IDs, no loans are processed."""
    # Scalars from an empty result set should be an empty list
    fake_db = _FakeSession([])

    _, _, _proc = _reload_with_fake_session(lambda: fake_db)
    processed = await _proc()

    assert processed == 0


@pytest.mark.anyio
async def test_process_overdue_loans_calls_process_for_each_batch_id():
    """
    process_overdue_loans dispatches one call to _process_single_loan per loan ID.

    Uses AsyncMock to count how many times _process_single_loan is called internally.
    """
    now = datetime.now(UTC)
    loan_a = _make_loan(
        loan_status=LoanStatus.ACTIVE,
        due_date=now - timedelta(hours=1),
    )
    loan_b = _make_loan(
        loan_status=LoanStatus.ACTIVE,
        due_date=now - timedelta(hours=2),
    )

    call_count = [0]

    def factory():
        call_count[0] += 1
        if call_count[0] == 1:
            # First session: batch SELECT — scalars().all() must return [ID1, ID2]
            return _FakeSession([loan_a.loan_id, loan_b.loan_id])
        return _FakeSession(None, None)  # _process_single_loan: loan not found

    _, _, _proc = _reload_with_fake_session(factory)

    # Patch _process_single_loan in the reloaded module so internal calls hit the mock
    import app.workers.overdue_worker as mod

    mock_proc = AsyncMock(return_value=True)
    with patch.object(mod, "_process_single_loan", mock_proc):
        processed = await _proc(now=now)

    assert processed == 2
    assert mock_proc.call_count == 2


# ---------------------------------------------------------------------------
# overdue_worker_loop (distributed lock)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_overdue_worker_loop_skips_when_lock_not_acquired():
    """When another worker holds the lock (NX returns None), the cycle is skipped."""
    with patch(
        "app.workers.overdue_worker.redis_client.set",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch(
            "app.workers.overdue_worker.process_overdue_loans",
            new_callable=AsyncMock,
        ) as mock_process:
            import asyncio

            from app.workers.overdue_worker import overdue_worker_loop

            stop = asyncio.Event()
            stop.set()

            await overdue_worker_loop(stop)

    mock_process.assert_not_called()


@pytest.mark.anyio
async def test_overdue_worker_loop_runs_when_lock_acquired():
    """When the distributed lock is acquired (NX succeeds), process_overdue_loans is called."""
    with patch(
        "app.workers.overdue_worker.redis_client.set",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with patch(
            "app.workers.overdue_worker.process_overdue_loans",
            new_callable=AsyncMock,
        ) as mock_process:
            import asyncio

            from app.workers.overdue_worker import overdue_worker_loop

            stop = asyncio.Event()
            # Stop the loop AFTER the first iteration is done
            mock_process.side_effect = lambda *args, **kwargs: stop.set() or 3
            await overdue_worker_loop(stop)

    assert mock_process.call_count == 1

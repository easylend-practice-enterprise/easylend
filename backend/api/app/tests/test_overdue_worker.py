import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.db.models import LoanStatus
from app.tests.conftest import _QueuedSession
from app.workers.overdue_worker import process_overdue_loans


def _make_overdue_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        user_id=kwargs.get("user_id", uuid.uuid4()),
        loan_status=kwargs.get("loan_status", LoanStatus.ACTIVE),
        due_date=kwargs.get("due_date"),
    )


@pytest.mark.anyio
async def test_process_overdue_loans_marks_loan_overdue_and_creates_audit():
    now = datetime.now(UTC)
    loan = _make_overdue_loan(
        loan_status=LoanStatus.ACTIVE,
        due_date=now - timedelta(hours=1),
    )

    # Execution order in process_overdue_loans:
    # [1] query overdue ACTIVE loans
    # [2] log_audit_event: most recent audit log row (inside log_audit_event)
    fake_db = _QueuedSession([loan], None)

    processed = await process_overdue_loans(fake_db, now=now)

    assert processed == 1
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
async def test_process_overdue_loans_no_matches_returns_zero():
    fake_db = _QueuedSession([])

    processed = await process_overdue_loans(fake_db)

    assert processed == 0
    assert fake_db.commit_calls == 0
    assert len(fake_db.added) == 0


@pytest.mark.anyio
async def test_process_overdue_loans_creates_audit_with_correct_payload():
    """Verify the audit payload contains the loan and asset IDs."""
    now = datetime.now(UTC)
    asset_id = uuid.uuid4()
    loan_id = uuid.uuid4()
    loan = _make_overdue_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        loan_status=LoanStatus.ACTIVE,
        due_date=now - timedelta(hours=1),
    )
    fake_db = _QueuedSession([loan], None)

    await process_overdue_loans(fake_db, now=now)

    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1

    audit_log = fake_db.added[0]
    assert audit_log.action_type == "LOAN_OVERDUE"
    assert audit_log.payload["loan_id"] == str(loan_id)
    assert audit_log.payload["asset_id"] == str(asset_id)


@pytest.mark.anyio
async def test_process_overdue_loans_transitions_status_to_overdue():
    """Verify the loan_status is mutated to OVERDUE on the returned object."""
    now = datetime.now(UTC)
    loan = _make_overdue_loan(
        loan_status=LoanStatus.ACTIVE,
        due_date=now - timedelta(hours=1),
    )
    fake_db = _QueuedSession([loan], None)

    await process_overdue_loans(fake_db, now=now)

    assert loan.loan_status == LoanStatus.OVERDUE

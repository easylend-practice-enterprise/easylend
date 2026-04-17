"""
Tests for the Loan Transaction endpoints: ELP-28.

Coverage:
    1. Auth/RBAC guard        : 401 without token
    2. GET /loans             : admin sees all, student scopes to own
    3. GET /loans/{id}/status : owner 200, wrong user 403
    4. POST /loans/checkout   : happy path 201, asset not found 400,
                                asset not available 400, lock contention 409
    5. POST /loans/return/initiate  : happy path 200, unknown loan 404,
                                wrong user 403, not active 400, no locker 503

_QueuedSession execute() ordering: every `await db.execute(query)` pops one
slot from the queue in FIFO order. Each test documents the exact slots used.
`await db.refresh(obj)` assigns a UUID to `loan_id` when it is None.
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

import app.api.v1.endpoints.loans as loans_endpoints
from app.core.websockets import manager
from app.db.models import UserStatus
from app.tests.conftest import (
    _bearer,
    _make_admin,
    _QueuedSession,
)


@pytest.fixture(autouse=True)
def mock_hardware_manager(monkeypatch):
    """
    Automatically mock the WebSocket manager during loan tests so the
    fail-fast hardware checks pass without needing a real Raspberry Pi.
    """

    class AlwaysConnectedDict(dict):
        def __contains__(self, key):
            return True

    monkeypatch.setattr(manager, "active_connections", AlwaysConnectedDict())
    monkeypatch.setattr(manager, "send_command", AsyncMock(return_value=True))


@pytest.fixture(autouse=True)
def mock_audit_logger(monkeypatch):
    """Mock log_audit_event so audit DB calls don't hit the fake session queue."""
    monkeypatch.setattr(loans_endpoints, "log_audit_event", AsyncMock())


@pytest.fixture(autouse=True)
def mock_idempotency_redis(monkeypatch):
    """Use per-test in-memory Redis emulation for idempotency keys."""

    class _FakeRedis:
        def __init__(self):
            self._keys: set[str] = set()

        async def exists(self, key: str) -> int:
            return 1 if key in self._keys else 0

        async def setex(self, key: str, ttl: int, value: str):  # noqa: ARG002
            self._keys.add(key)

        async def delete(self, key: str) -> int:
            if key in self._keys:
                self._keys.discard(key)
                return 1
            return 0

        async def set(
            self,
            key: str,
            value: str,
            ex: int | None = None,
            nx: bool = False,  # noqa: ARG002
        ) -> bool:
            if nx and key in self._keys:
                return False
            self._keys.add(key)
            return True

    monkeypatch.setattr(loans_endpoints, "redis_client", _FakeRedis())


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_student(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=kwargs.get("user_id", uuid.uuid4()),
        role_id=uuid.uuid4(),
        first_name="Student",
        last_name="Test",
        email="student@easylend.be",
        nfc_tag_id=None,
        pin_hash="hashed",
        failed_login_attempts=0,
        locked_until=None,
        status=UserStatus.ACTIVE,
        ban_reason=None,
        role=SimpleNamespace(role_name="Student"),
    )


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        category_id=uuid.uuid4(),
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        name=kwargs.get("name", "HP EliteBook"),
        aztec_code=kwargs.get("aztec_code", "AZT-001"),
        asset_status=kwargs.get("asset_status", "AVAILABLE"),
        is_deleted=kwargs.get("is_deleted", False),
    )


def _make_locker(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        logical_number=kwargs.get("logical_number", 1),
        locker_status=kwargs.get("locker_status", "AVAILABLE"),
    )


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        user_id=kwargs.get("user_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id", uuid.uuid4()),
        return_locker_id=kwargs.get("return_locker_id", None),
        reserved_at=kwargs.get("reserved_at", None),
        borrowed_at=kwargs.get("borrowed_at", None),
        due_date=kwargs.get("due_date", None),
        returned_at=kwargs.get("returned_at", None),
        loan_status=kwargs.get("loan_status", "ACTIVE"),
        evaluations=[],  # eager-loaded by export; empty list for test fixtures
    )


def _with_idempotency(headers: dict, key: str) -> dict:
    merged = dict(headers)
    merged["Idempotency-Key"] = key
    return merged


# ---------------------------------------------------------------------------
# A _QueuedSession subclass that can simulate an OperationalError on execute
# ---------------------------------------------------------------------------


class _LockingSession(_QueuedSession):
    """Like _QueuedSession but raises OperationalError on the 2nd execute call.

    Use this to simulate a locked row (FOR UPDATE NOWAIT contention).
    Queue slot [1] is consumed by get_current_user; execute #2 raises.
    """

    def __init__(self, *results):
        super().__init__(*results)
        self._call_count = 0

    async def execute(self, query):
        self._call_count += 1
        if self._call_count == 2:  # 1st is get_current_user, 2nd is FOR UPDATE NOWAIT
            raise OperationalError(
                "could not obtain lock",
                params=None,
                orig=Exception("lock not available"),
            )
        return await super().execute(query)


class _LockerLockingSession(_QueuedSession):
    """Raises OperationalError on locker lock (3rd execute call)."""

    def __init__(self, *results):
        super().__init__(*results)
        self._call_count = 0

    async def execute(self, query):
        self._call_count += 1
        if self._call_count == 3:
            raise OperationalError(
                "lock not available",
                params=None,
                orig=Exception("lock not available"),
            )
        return await super().execute(query)


class _LoanLockingSession(_QueuedSession):
    """Raises OperationalError on loan lock (4th execute call)."""

    def __init__(self, *results):
        super().__init__(*results)
        self._call_count = 0

    async def execute(self, query):
        self._call_count += 1
        if self._call_count == 4:
            raise OperationalError(
                "lock not available",
                params=None,
                orig=Exception("lock not available"),
            )
        return await super().execute(query)


# ---------------------------------------------------------------------------
# 1. Auth guard
# ---------------------------------------------------------------------------


def test_list_loans_returns_401_without_token(client_with_overrides):
    """GET /loans without any Bearer token → 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/loans")
    assert response.status_code == 401


def test_get_loan_status_returns_401_without_token(client_with_overrides):
    """GET /loans/{id}/status without any Bearer token → 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get(f"/api/v1/loans/{uuid.uuid4()}/status")
    assert response.status_code == 401


def test_checkout_returns_401_without_token(client_with_overrides):
    """POST /loans/checkout without any Bearer token → 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": "AZT-001"},
            headers={"Idempotency-Key": "checkout-401"},
        )
    assert response.status_code == 401


def test_return_initiate_returns_401_without_token(client_with_overrides):
    """POST /loans/return/initiate without any Bearer token → 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={"loan_id": str(uuid.uuid4()), "kiosk_id": str(uuid.uuid4())},
            headers={"Idempotency-Key": "return-401"},
        )
    assert response.status_code == 401


def test_checkout_returns_400_when_idempotency_header_missing(client_with_overrides):
    """POST /loans/checkout with auth but no Idempotency-Key header → 400."""
    student = _make_student()
    with client_with_overrides(_QueuedSession(student)) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": "AZT-001"},
            headers=_bearer(student),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Idempotency-Key header is required"


def test_return_initiate_returns_400_when_idempotency_header_missing(
    client_with_overrides,
):
    """POST /loans/return/initiate with auth but no Idempotency-Key header → 400."""
    student = _make_student()
    with client_with_overrides(_QueuedSession(student)) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={"loan_id": str(uuid.uuid4()), "kiosk_id": str(uuid.uuid4())},
            headers=_bearer(student),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Idempotency-Key header is required"


# ---------------------------------------------------------------------------
# 2. GET /loans
# ---------------------------------------------------------------------------


def test_list_loans_admin_sees_all_loans(client_with_overrides):
    """GET /loans as admin returns all loans in the system.

    DB execute order:
    [1] get_current_user → admin
    [2] list query       → [loan_a, loan_b]
    [3] count query      → 2
    """
    admin = _make_admin()
    loan_a = _make_loan()
    loan_b = _make_loan()

    fake_db = _QueuedSession(admin, [loan_a, loan_b], 2)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/loans", headers=_bearer(admin))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_loans_student_sees_only_own(client_with_overrides):
    """GET /loans as a student returns only their own loans.

    DB execute order:
    [1] get_current_user → student
    [2] scoped list      → [own_loan]
    [3] scoped count     → 1
    """
    student = _make_student()
    own_loan = _make_loan(user_id=student.user_id)

    fake_db = _QueuedSession(student, [own_loan], 1)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/loans", headers=_bearer(student))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


# ---------------------------------------------------------------------------
# 3. GET /loans/{loan_id}/status
# ---------------------------------------------------------------------------


def test_get_loan_status_returns_200_for_owner(client_with_overrides):
    """GET /loans/{id}/status for the loan owner → 200 with loan_status.

    DB execute order:
    [1] get_current_user   → student
    [2] _get_loan_or_404   → loan (same user_id)
    """
    student = _make_student()
    loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")

    fake_db = _QueuedSession(student, loan)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/loans/{loan.loan_id}/status", headers=_bearer(student)
        )

    assert response.status_code == 200
    data = response.json()
    assert data["loan_status"] == "ACTIVE"
    assert data["loan_id"] == str(loan.loan_id)


def test_get_loan_status_returns_403_for_wrong_user(client_with_overrides):
    """GET /loans/{id}/status by a different (non-admin) user → 403.

    DB execute order:
    [1] get_current_user   → student_b
    [2] _get_loan_or_404   → loan (owned by student_a)
    """
    student_b = _make_student()
    other_user_id = uuid.uuid4()
    loan = _make_loan(user_id=other_user_id)  # owned by someone else

    fake_db = _QueuedSession(student_b, loan)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/loans/{loan.loan_id}/status", headers=_bearer(student_b)
        )

    assert response.status_code == 403


def test_get_loan_status_returns_200_for_admin_on_any_loan(client_with_overrides):
    """GET /loans/{id}/status as admin can access any loan.

    DB execute order:
    [1] get_current_user   → admin
    [2] _get_loan_or_404   → loan (different user_id)
    """
    admin = _make_admin()
    loan = _make_loan(user_id=uuid.uuid4(), loan_status="RETURNING")

    fake_db = _QueuedSession(admin, loan)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/loans/{loan.loan_id}/status", headers=_bearer(admin)
        )

    assert response.status_code == 200
    assert response.json()["loan_status"] == "RETURNING"


# ---------------------------------------------------------------------------
# 4. POST /loans/checkout
# ---------------------------------------------------------------------------


def test_checkout_returns_202_on_happy_path(client_with_overrides):
    """POST /checkout with a valid aztec_code creates a loan and returns 202.

    DB execute order:
    [1] get_current_user      → student
    [2] SELECT asset FOR UPDATE NOWAIT → available asset (with locker_id)
    [3] SELECT locker FOR UPDATE NOWAIT → locker
    (db.add + commit + refresh)
    """
    student = _make_student()
    locker_id = uuid.uuid4()
    asset = _make_asset(asset_status="AVAILABLE", locker_id=locker_id)
    locker = _make_locker(locker_id=locker_id, locker_status="OCCUPIED")

    fake_db = _QueuedSession(student, asset, locker)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": asset.aztec_code},
            headers=_with_idempotency(_bearer(student), "checkout-happy"),
        )

    assert response.status_code == 202
    data = response.json()
    assert data["loan_status"] == "RESERVED"
    assert data["asset_id"] == str(asset.asset_id)
    assert data["checkout_locker_id"] == str(locker_id)
    # Verify side-effects: checkout reserves the loan and borrows the asset,
    # but physical locker release is deferred until Vision confirmation.
    assert asset.locker_id == locker_id
    assert asset.asset_status == "BORROWED"
    assert locker.locker_status == "OCCUPIED"
    assert fake_db.commit_calls == 1


def test_checkout_returns_503_when_manager_send_command_returns_false(
    monkeypatch, client_with_overrides
):
    """If the WebSocket manager fails to send the `open_slot` command,
    the checkout should commit the DB state first, then return 503.
    The RESERVED loan remains in the database; the timeout worker will clean it up.
    """
    student = _make_student()
    locker_id = uuid.uuid4()
    asset = _make_asset(asset_status="AVAILABLE", locker_id=locker_id)
    locker = _make_locker(locker_id=locker_id, locker_status="OCCUPIED")

    fake_db = _QueuedSession(student, asset, locker)

    # Simulate failing send_command (hardware unreachable despite an active connection)
    monkeypatch.setattr(manager, "send_command", AsyncMock(return_value=False))

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": asset.aztec_code},
            headers=_with_idempotency(_bearer(student), "checkout-sendcmd-fails"),
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Unable to initiate checkout: kiosk hardware unavailable. Please try again."
    )
    # DB is committed first so the loan record is durable; no rollback occurs.
    assert fake_db.commit_calls == 1
    assert fake_db.rollback_calls == 0


def test_return_initiate_returns_503_when_manager_send_command_returns_false(
    monkeypatch, client_with_overrides
):
    """If the WebSocket manager fails to send the `open_slot` command,
    the return initiation should commit the DB state first, then return 503.
    The RETURNING loan remains in the database; the timeout worker will clean it up.
    """
    student = _make_student()
    active_loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")
    free_locker = _make_locker(kiosk_id=_VALID_KIOSK_ID, locker_status="AVAILABLE")

    # Queue: [auth user, kiosk exists, loan, locked loan, free_locker]
    fake_db = _QueuedSession(
        student, SimpleNamespace(), active_loan, active_loan, free_locker
    )

    monkeypatch.setattr(manager, "send_command", AsyncMock(return_value=False))

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={
                "loan_id": str(active_loan.loan_id),
                "kiosk_id": str(_VALID_KIOSK_ID),
            },
            headers=_with_idempotency(_bearer(student), "return-sendcmd-fails"),
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Unable to initiate return: kiosk hardware unavailable. Please try again."
    )
    # DB is committed first so the loan record is durable; no rollback occurs.
    assert fake_db.commit_calls == 1
    assert fake_db.rollback_calls == 0


def test_checkout_returns_400_when_asset_not_found(client_with_overrides):
    """POST /checkout with unknown aztec_code → 400.

    DB execute order:
    [1] get_current_user → student
    [2] asset query      → None (not found)
    """
    student = _make_student()
    fake_db = _QueuedSession(student, None)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": "DOES-NOT-EXIST"},
            headers=_with_idempotency(_bearer(student), "checkout-not-found"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Asset not found."
    assert fake_db.commit_calls == 0


def test_checkout_returns_400_when_asset_not_available(client_with_overrides):
    """POST /checkout on a BORROWED asset → 400.

    DB execute order:
    [1] get_current_user → student
    [2] asset query      → asset with status=BORROWED
    """
    student = _make_student()
    borrowed_asset = _make_asset(asset_status="BORROWED")

    fake_db = _QueuedSession(student, borrowed_asset)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": borrowed_asset.aztec_code},
            headers=_with_idempotency(_bearer(student), "checkout-not-available"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Asset is not available for checkout."
    assert fake_db.commit_calls == 0


def test_checkout_returns_400_when_asset_has_no_locker(client_with_overrides):
    """POST /checkout for an asset without locker_id returns 400."""
    student = _make_student()
    orphaned_asset = _make_asset(asset_status="AVAILABLE", locker_id=None)

    fake_db = _QueuedSession(student, orphaned_asset)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": orphaned_asset.aztec_code},
            headers=_with_idempotency(_bearer(student), "checkout-no-locker"),
        )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Asset has no assigned locker and cannot be checked out."
    )
    assert fake_db.commit_calls == 0


def test_checkout_returns_409_on_lock_contention(client_with_overrides):
    """POST /checkout when the asset row is locked by another TX → 409.

    The _LockingSession raises OperationalError on the 2nd execute call
    (which is the FOR UPDATE NOWAIT on the asset).
    """
    student = _make_student()
    # Queue: [0] student (for get_current_user), execute #2 raises OperationalError
    locking_db = _LockingSession(student)
    with client_with_overrides(locking_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": "AZT-LOCKED"},
            headers=_with_idempotency(_bearer(student), "checkout-lock-contention"),
        )

    assert response.status_code == 409
    assert "currently being processed" in response.json()["detail"]
    assert locking_db.commit_calls == 0


def test_checkout_returns_409_on_locker_lock_contention(client_with_overrides):
    """POST /checkout returns 409 when locker row lock is contended."""
    student = _make_student()
    asset = _make_asset(asset_status="AVAILABLE", locker_id=uuid.uuid4())

    locking_db = _LockerLockingSession(student, asset)
    with client_with_overrides(locking_db) as client:
        response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": asset.aztec_code},
            headers=_with_idempotency(_bearer(student), "checkout-locker-contention"),
        )

    assert response.status_code == 409
    assert "currently being processed" in response.json()["detail"]
    assert locking_db.commit_calls == 0


def test_checkout_returns_409_for_duplicate_idempotency_key(client_with_overrides):
    """Second checkout request with the same Idempotency-Key returns 409."""

    student = _make_student()
    locker_id = uuid.uuid4()
    asset = _make_asset(asset_status="AVAILABLE", locker_id=locker_id)
    locker = _make_locker(locker_id=locker_id, locker_status="OCCUPIED")
    idem_key = "checkout-idempotent-dup"

    first_db = _QueuedSession(student, asset, locker)
    with client_with_overrides(first_db) as client:
        first_response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": asset.aztec_code},
            headers=_with_idempotency(_bearer(student), idem_key),
        )

    second_db = _QueuedSession(student)
    with client_with_overrides(second_db) as client:
        second_response = client.post(
            "/api/v1/loans/checkout",
            json={"aztec_code": asset.aztec_code},
            headers=_with_idempotency(_bearer(student), idem_key),
        )

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert (
        second_response.json()["detail"]
        == "Duplicate request with this idempotency key is already being processed or has completed."
    )
    assert second_db.commit_calls == 0


# ---------------------------------------------------------------------------
# 5. POST /loans/return/initiate
# ---------------------------------------------------------------------------

_VALID_KIOSK_ID = uuid.uuid4()


def test_return_initiate_returns_202_on_happy_path(client_with_overrides):
    """POST /return/initiate for an active loan assigns a return locker → 202.

    DB execute order:
    [1] get_current_user      → student
    [2] kiosk query           → kiosk object (exists)
    [3] _get_loan_or_404      → active loan (same user)
    [4] lock loan row         → active loan (locked)
    [5] free locker query     → available locker
    """
    student = _make_student()
    loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")
    free_locker = _make_locker(kiosk_id=_VALID_KIOSK_ID, locker_status="AVAILABLE")

    fake_db = _QueuedSession(student, SimpleNamespace(), loan, loan, free_locker)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={"loan_id": str(loan.loan_id), "kiosk_id": str(_VALID_KIOSK_ID)},
            headers=_with_idempotency(_bearer(student), "return-happy"),
        )
    assert response.status_code == 202
    data = response.json()
    assert data["loan_status"] == "RETURNING"
    assert data["return_locker_id"] == str(free_locker.locker_id)
    # Side-effects
    assert loan.loan_status == "RETURNING"
    assert loan.return_locker_id == free_locker.locker_id
    assert free_locker.locker_status == "OCCUPIED"
    assert fake_db.commit_calls == 1


def test_return_initiate_returns_404_for_unknown_loan(client_with_overrides):
    """POST /return/initiate with an unknown loan_id → 404.

    DB execute order:
    [1] get_current_user → student
    [2] kiosk query      → kiosk object (exists)
    [3] loan query       → None → 404
    """
    student = _make_student()
    fake_db = _QueuedSession(student, SimpleNamespace(), None)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={"loan_id": str(uuid.uuid4()), "kiosk_id": str(_VALID_KIOSK_ID)},
            headers=_with_idempotency(_bearer(student), "return-unknown-loan"),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Loan not found."


def test_return_initiate_returns_403_for_wrong_user(client_with_overrides):
    """POST /return/initiate on another user's loan by a non-admin → 403.

    DB execute order:
    [1] get_current_user → student_b
    [2] kiosk query      → kiosk object (exists)
    [3] loan query       → loan owned by student_a
    """
    student_b = _make_student()
    loan = _make_loan(user_id=uuid.uuid4())  # owned by someone else

    fake_db = _QueuedSession(student_b, SimpleNamespace(), loan)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={"loan_id": str(loan.loan_id), "kiosk_id": str(_VALID_KIOSK_ID)},
            headers=_with_idempotency(_bearer(student_b), "return-wrong-user"),
        )

    assert response.status_code == 403


def test_return_initiate_returns_400_when_loan_not_active(client_with_overrides):
    """POST /return/initiate on a COMPLETED loan → 400.

    DB execute order:
    [1] get_current_user → student
    [2] kiosk query      → kiosk object (exists)
    [3] loan query       → loan with status=COMPLETED
    """
    student = _make_student()
    completed_loan = _make_loan(user_id=student.user_id, loan_status="COMPLETED")

    fake_db = _QueuedSession(student, SimpleNamespace(), completed_loan)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={
                "loan_id": str(completed_loan.loan_id),
                "kiosk_id": str(_VALID_KIOSK_ID),
            },
            headers=_with_idempotency(_bearer(student), "return-not-active"),
        )

    assert response.status_code == 400
    assert "not active" in response.json()["detail"]
    assert fake_db.commit_calls == 0


def test_return_initiate_returns_503_when_no_locker_available(client_with_overrides):
    """POST /return/initiate when all lockers at the kiosk are occupied → 503.

    DB execute order:
    [1] get_current_user      → student
    [2] kiosk query           → kiosk object (exists)
    [3] loan query            → active loan
    [4] lock loan row         → active loan (locked)
    [5] free locker query     → None (no available locker)
    """
    student = _make_student()
    active_loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")

    fake_db = _QueuedSession(student, SimpleNamespace(), active_loan, active_loan, None)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={
                "loan_id": str(active_loan.loan_id),
                "kiosk_id": str(_VALID_KIOSK_ID),
            },
            headers=_with_idempotency(_bearer(student), "return-no-locker"),
        )
    assert response.status_code == 503
    assert "No available lockers" in response.json()["detail"]
    assert fake_db.commit_calls == 0


def test_return_initiate_returns_404_for_unknown_kiosk(client_with_overrides):
    """POST /return/initiate with an unknown kiosk_id → 404.

    DB execute order:
    [1] get_current_user      → student
    [2] kiosk query           → None (kiosk does not exist)
    """
    student = _make_student()
    fake_db = _QueuedSession(student, None)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={
                "loan_id": str(uuid.uuid4()),
                "kiosk_id": str(uuid.uuid4()),  # non-existent kiosk
            },
            headers=_with_idempotency(_bearer(student), "return-unknown-kiosk"),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Kiosk not found."
    assert fake_db.commit_calls == 0


def test_return_initiate_returns_409_on_loan_lock_contention(client_with_overrides):
    """POST /return/initiate returns 409 when loan lock is contended."""
    student = _make_student()
    active_loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")

    locking_db = _LoanLockingSession(student, SimpleNamespace(), active_loan)
    with client_with_overrides(locking_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={
                "loan_id": str(active_loan.loan_id),
                "kiosk_id": str(_VALID_KIOSK_ID),
            },
            headers=_with_idempotency(_bearer(student), "return-loan-lock"),
        )

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]
    assert locking_db.commit_calls == 0


def test_return_initiate_returns_409_when_loan_state_changed_concurrently(
    client_with_overrides,
):
    """POST /return/initiate returns 409 when lock query no longer matches."""
    student = _make_student()
    active_loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")

    fake_db = _QueuedSession(student, SimpleNamespace(), active_loan, None)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/loans/return/initiate",
            json={
                "loan_id": str(active_loan.loan_id),
                "kiosk_id": str(_VALID_KIOSK_ID),
            },
            headers=_with_idempotency(_bearer(student), "return-loan-state-changed"),
        )

    assert response.status_code == 409
    assert "no longer in a state" in response.json()["detail"]
    assert fake_db.commit_calls == 0


def test_return_initiate_returns_409_for_duplicate_idempotency_key(
    client_with_overrides,
):
    """POST /return/initiate with a reused Idempotency-Key returns 409."""
    student = _make_student()
    loan = _make_loan(user_id=student.user_id, loan_status="ACTIVE")
    free_locker = _make_locker(kiosk_id=_VALID_KIOSK_ID, locker_status="AVAILABLE")

    # Queue slots:
    # First request:  [1] auth user, [2] kiosk, [3] loan, [4] locked loan, [5] locker
    # Second request: [6] auth user (idempotency 409 happens before endpoint DB queries)
    fake_db = _QueuedSession(
        student, SimpleNamespace(), loan, loan, free_locker, student
    )

    with client_with_overrides(fake_db) as client:
        payload = {
            "loan_id": str(loan.loan_id),
            "kiosk_id": str(_VALID_KIOSK_ID),
        }
        headers = _with_idempotency(_bearer(student), "duplicate-return-key-123")

        response1 = client.post(
            "/api/v1/loans/return/initiate", json=payload, headers=headers
        )
        assert response1.status_code == 202

        response2 = client.post(
            "/api/v1/loans/return/initiate", json=payload, headers=headers
        )
        assert response2.status_code == 409
        assert (
            response2.json()["detail"]
            == "Duplicate request with this idempotency key is already being processed or has completed."
        )
    assert fake_db.commit_calls == 1


# ---------------------------------------------------------------------------
# 6. POST /loans/{loan_id}/report-damage
# ---------------------------------------------------------------------------


def test_report_damage_returns_400_when_idempotency_header_missing(
    client_with_overrides,
):
    student = _make_student()
    with client_with_overrides(_QueuedSession(student)) as client:
        response = client.post(
            f"/api/v1/loans/{uuid.uuid4()}/report-damage",
            headers=_bearer(student),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Idempotency-Key header is required"


def test_report_damage_returns_200_and_suspends_current_and_previous_users(
    client_with_overrides,
):
    student = _make_student()
    current_user_row = _make_student(user_id=student.user_id)

    locker_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    loan = _make_loan(
        user_id=student.user_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="ACTIVE",
        borrowed_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    asset = _make_asset(
        asset_id=asset_id,
        locker_id=locker_id,
        asset_status="BORROWED",
    )
    locker = _make_locker(
        locker_id=locker_id,
        locker_status="AVAILABLE",
    )

    previous_user_row = _make_student()
    previous_loan = _make_loan(
        user_id=previous_user_row.user_id,
        asset_id=asset_id,
        loan_status="COMPLETED",
        returned_at=datetime.now(UTC) - timedelta(days=1),
    )

    fake_db = _QueuedSession(
        student,
        loan,
        asset,
        locker,
        current_user_row,
        previous_loan,
        previous_user_row,
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/loans/{loan.loan_id}/report-damage",
            headers=_with_idempotency(_bearer(student), "report-damage-happy"),
        )

    assert response.status_code == 200
    assert response.json()["loan_status"] == "DISPUTED"
    assert loan.loan_status == "DISPUTED"
    assert asset.asset_status == "MAINTENANCE"
    assert locker.locker_status == "MAINTENANCE"
    assert current_user_row.locked_until is not None
    assert previous_user_row.locked_until is not None
    assert fake_db.commit_calls == 1
    send_command_mock = cast(AsyncMock, manager.send_command)
    send_command_mock.assert_awaited_once()
    assert send_command_mock.await_args is not None
    sent_kiosk_id, sent_payload = send_command_mock.await_args.args
    assert sent_kiosk_id == str(locker.kiosk_id)
    assert sent_payload["action"] == "set_led"
    assert sent_payload["color"] == "orange"
    assert sent_payload["locker_id"] == locker.logical_number
    assert isinstance(sent_payload["locker_id"], int)


def test_report_damage_returns_400_when_grace_period_expired(client_with_overrides):
    student = _make_student()

    locker_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    expired_loan = _make_loan(
        user_id=student.user_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="ACTIVE",
        borrowed_at=datetime.now(UTC) - timedelta(minutes=6),
    )
    asset = _make_asset(asset_id=asset_id, locker_id=locker_id, asset_status="BORROWED")
    locker = _make_locker(locker_id=locker_id, locker_status="AVAILABLE")

    fake_db = _QueuedSession(student, expired_loan, asset, locker)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/loans/{expired_loan.loan_id}/report-damage",
            headers=_with_idempotency(_bearer(student), "report-damage-expired"),
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Grace period has expired for damage reporting."
    assert fake_db.commit_calls == 0


def test_report_damage_returns_403_for_non_owner(client_with_overrides):
    student = _make_student()
    foreign_loan = _make_loan(user_id=uuid.uuid4(), loan_status="ACTIVE")

    fake_db = _QueuedSession(student, foreign_loan)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/loans/{foreign_loan.loan_id}/report-damage",
            headers=_with_idempotency(_bearer(student), "report-damage-forbidden"),
        )

    assert response.status_code == 403


def test_report_damage_returns_200_when_hardware_sync_fails(
    monkeypatch,
    client_with_overrides,
):
    student = _make_student()
    current_user_row = _make_student(user_id=student.user_id)

    locker_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    loan = _make_loan(
        user_id=student.user_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="FRAUD_SUSPECTED",
        borrowed_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    asset = _make_asset(asset_id=asset_id, locker_id=locker_id, asset_status="BORROWED")
    locker = _make_locker(locker_id=locker_id, locker_status="AVAILABLE")

    fake_db = _QueuedSession(
        student,
        loan,
        asset,
        locker,
        current_user_row,
        None,
    )
    monkeypatch.setattr(manager, "send_command", AsyncMock(return_value=False))

    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/loans/{loan.loan_id}/report-damage",
            headers=_with_idempotency(_bearer(student), "report-damage-hw-fail"),
        )

    assert response.status_code == 200
    assert response.json()["loan_status"] == "DISPUTED"
    assert fake_db.commit_calls == 1


def test_report_damage_rate_limit_before_idempotency_does_not_lock_key(
    monkeypatch,
    client_with_overrides,
):
    student = _make_student()

    monkeypatch.setattr(
        loans_endpoints,
        "check_token_rate_limit",
        AsyncMock(
            side_effect=HTTPException(status_code=429, detail="Too many requests")
        ),
    )

    with client_with_overrides(_QueuedSession(student)) as client:
        first = client.post(
            f"/api/v1/loans/{uuid.uuid4()}/report-damage",
            headers=_with_idempotency(_bearer(student), "report-damage-rate-limit"),
        )

    assert first.status_code == 429

    monkeypatch.setattr(
        loans_endpoints,
        "check_token_rate_limit",
        AsyncMock(return_value=None),
    )

    locker_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    loan = _make_loan(
        user_id=student.user_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="ACTIVE",
        borrowed_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    asset = _make_asset(asset_id=asset_id, locker_id=locker_id, asset_status="BORROWED")
    locker = _make_locker(locker_id=locker_id, locker_status="AVAILABLE")
    current_user_row = _make_student(user_id=student.user_id)

    fake_db = _QueuedSession(
        student,
        loan,
        asset,
        locker,
        current_user_row,
        None,
    )

    with client_with_overrides(fake_db) as client:
        second = client.post(
            f"/api/v1/loans/{loan.loan_id}/report-damage",
            headers=_with_idempotency(_bearer(student), "report-damage-rate-limit"),
        )

    assert second.status_code == 200
    assert second.json()["loan_status"] == "DISPUTED"

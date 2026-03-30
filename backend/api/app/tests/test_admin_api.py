"""
Tests for the Admin Quarantine Dashboard endpoints (ELP-10 Step 10c).

Coverage:
    1. RBAC: non-admin user → 403 Forbidden
    2. GET /admin/quarantine → 200 with PENDING_INSPECTION loans
    3. GET /admin/evaluations/{loan_id} → 200 with latest evaluation
    4. PATCH /admin/evaluations/{evaluation_id}/judge:
         - is_approved=True  → loan DISPUTED, asset MAINTENANCE
         - is_approved=False (CHECKOUT) → loan ACTIVE, asset BORROWED, locker AVAILABLE
         - is_approved=False (RETURN)   → loan COMPLETED, asset AVAILABLE, locker OCCUPIED
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.tests.conftest import _bearer, _make_admin, _make_medewerker, _QueuedSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        category_id=uuid.uuid4(),
        locker_id=kwargs.get("locker_id"),
        name=kwargs.get("name", "HP EliteBook"),
        aztec_code=kwargs.get("aztec_code", "AZT-001"),
        asset_status=kwargs.get("asset_status", "PENDING_INSPECTION"),
        is_deleted=False,
    )


def _make_locker(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        logical_number=kwargs.get("logical_number", 1),
        locker_status=kwargs.get("locker_status", "MAINTENANCE"),
    )


def _make_kiosk(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        name=kwargs.get("name", "Kiosk-A"),
    )


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        user_id=kwargs.get("user_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id", uuid.uuid4()),
        return_locker_id=kwargs.get("return_locker_id"),
        reserved_at=None,
        borrowed_at=kwargs.get("borrowed_at"),
        due_date=None,
        returned_at=None,
        loan_status=kwargs.get("loan_status", "PENDING_INSPECTION"),
        asset=None,
        user=None,
        checkout_locker=None,
        return_locker=None,
    )


def _make_evaluation(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        evaluation_id=kwargs.get("evaluation_id", uuid.uuid4()),
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        evaluation_type=kwargs.get("evaluation_type", "CHECKOUT"),
        photo_url=kwargs.get("photo_url", "/api/v1/images/test.jpg"),
        ai_confidence=kwargs.get("ai_confidence", 0.95),
        has_damage_detected=kwargs.get("has_damage_detected", True),
        detected_objects=kwargs.get("detected_objects", {"detections": []}),
        model_version=kwargs.get("model_version", "yolo26-dual-model"),
        is_approved=None,
        rejection_reason=None,
        analyzed_at=kwargs.get("analyzed_at", datetime.now(UTC)),
        loan=None,
    )


class _QuarantineListResult:
    """Returns pre-built loans directly, bypassing joinedload ORM proxies."""

    def __init__(self, loans: list[SimpleNamespace]):
        self._loans = loans

    def unique(self):
        return self

    def scalars(self):
        return self

    def all(self) -> list:
        return self._loans


class _QuarantineSession(_QueuedSession):
    """
    Bypasses joinedload in the /quarantine endpoint so that our manually-
    constructed SimpleNamespace objects (with pre-set kiosk relations) are
    returned directly instead of ORM relationship proxies.
    """

    def __init__(self, admin: SimpleNamespace, loans: list[SimpleNamespace]):
        super().__init__(admin)
        self._loans = loans

    async def execute(self, query):
        result = await super().execute(query)
        query_str = str(query)
        if "FROM loans" in query_str:
            return _QuarantineListResult(self._loans)
        return result


# ---------------------------------------------------------------------------
# 1. RBAC guard
# ---------------------------------------------------------------------------


def test_quarantine_returns_403_for_non_admin(client_with_overrides):
    """GET /admin/quarantine without admin role → 403 Forbidden."""

    student = _make_medewerker()

    fake_db = _QueuedSession(student)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/admin/quarantine", headers=_bearer(student))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions."


# ---------------------------------------------------------------------------
# 2. GET /admin/quarantine
# ---------------------------------------------------------------------------


def test_quarantine_returns_200_with_quarantined_loans(client_with_overrides):
    """GET /admin/quarantine returns PENDING_INSPECTION loans with joined relation names."""

    admin = _make_admin()
    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    kiosk = _make_kiosk(kiosk_id=kiosk_id, name="Kiosk-B")
    locker = _make_locker(locker_id=locker_id, kiosk_id=kiosk_id)
    locker.kiosk = kiosk  # type: ignore[attr-defined]
    asset = _make_asset(asset_id=asset_id, name="Dell Latitude")
    user = SimpleNamespace(
        first_name="Jane", last_name="Doe", role=SimpleNamespace(role_name="Student")
    )
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="PENDING_INSPECTION",
        borrowed_at=None,
        returned_at=None,
    )
    loan.asset = asset  # type: ignore[attr-defined]
    loan.user = user  # type: ignore[attr-defined]
    loan.checkout_locker = locker  # type: ignore[attr-defined]
    loan.return_locker = None  # type: ignore[attr-defined]

    fake_db = _QuarantineSession(admin, [loan])
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/admin/quarantine", headers=_bearer(admin))

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["loan_id"] == str(loan_id)
    assert data[0]["asset_name"] == "Dell Latitude"
    assert data[0]["user_name"] == "Jane Doe"
    assert data[0]["kiosk_name"] == "Kiosk-B"
    assert data[0]["loan_status"] == "PENDING_INSPECTION"


def test_quarantine_returns_empty_list_when_no_quarantined_loans(client_with_overrides):
    """GET /admin/quarantine returns an empty list when no loans are in quarantine."""

    admin = _make_admin()

    fake_db = _QuarantineSession(admin, [])
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/admin/quarantine", headers=_bearer(admin))

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# 3. GET /admin/evaluations/{loan_id}
# ---------------------------------------------------------------------------


def test_get_evaluation_returns_200_with_latest_evaluation(client_with_overrides):
    """GET /admin/evaluations/{loan_id} returns the most recent evaluation for the loan."""

    admin = _make_admin()
    loan_id = uuid.uuid4()
    eval_id = uuid.uuid4()

    evaluation = _make_evaluation(
        evaluation_id=eval_id,
        loan_id=loan_id,
        evaluation_type="CHECKOUT",
        ai_confidence=0.92,
        has_damage_detected=False,
    )

    fake_db = _QueuedSession(admin, evaluation)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/admin/evaluations/{loan_id}", headers=_bearer(admin)
        )

    assert response.status_code == 200
    data = response.json()
    assert data["evaluation_id"] == str(eval_id)
    assert data["evaluation_type"] == "CHECKOUT"
    assert data["ai_confidence"] == 0.92
    assert data["has_damage_detected"] is False


def test_get_evaluation_returns_404_when_no_evaluation_found(client_with_overrides):
    """GET /admin/evaluations/{loan_id} returns 404 when no evaluation exists."""

    admin = _make_admin()
    loan_id = uuid.uuid4()

    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/admin/evaluations/{loan_id}", headers=_bearer(admin)
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "No evaluation found for this loan."


# ---------------------------------------------------------------------------
# 4. PATCH /admin/evaluations/{evaluation_id}/judge
# ---------------------------------------------------------------------------


def _make_judge_session(admin, evaluation, loan, asset, locker):
    """
    Build a _QueuedSession for the judge endpoint.

    execute() order:
        [0] get_current_user  → admin
        [1] lock evaluation   → evaluation
        [2] lock loan         → loan
        [3] lock asset        → asset
        [4] lock locker       → locker (if locker is not None)
    """
    if locker is not None:
        return _QueuedSession(admin, evaluation, loan, asset, locker)
    return _QueuedSession(admin, evaluation, loan, asset)


def test_judge_approved_sets_loan_disputed_and_asset_maintenance(
    client_with_overrides,
):
    """is_approved=True → loan → DISPUTED, asset → MAINTENANCE, locker → MAINTENANCE."""

    admin = _make_admin()
    eval_id = uuid.uuid4()
    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()

    evaluation = _make_evaluation(
        evaluation_id=eval_id,
        loan_id=loan_id,
        evaluation_type="CHECKOUT",
    )
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="PENDING_INSPECTION",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="PENDING_INSPECTION")
    locker = _make_locker(locker_id=locker_id, locker_status="MAINTENANCE")

    fake_db = _make_judge_session(admin, evaluation, loan, asset, locker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/admin/evaluations/{eval_id}/judge",
            headers=_bearer(admin),
            json={"is_approved": True},
        )

    assert response.status_code == 204
    assert evaluation.is_approved is True
    assert loan.loan_status == "DISPUTED"
    assert asset.asset_status == "MAINTENANCE"
    assert locker.locker_status == "MAINTENANCE"
    assert fake_db.commit_calls == 1


def test_judge_rejected_checkout_reverts_to_active_and_borrowed(
    client_with_overrides,
):
    """is_approved=False on CHECKOUT → loan ACTIVE, asset BORROWED, locker AVAILABLE."""

    admin = _make_admin()
    eval_id = uuid.uuid4()
    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()

    evaluation = _make_evaluation(
        evaluation_id=eval_id,
        loan_id=loan_id,
        evaluation_type="CHECKOUT",
    )
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="PENDING_INSPECTION",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="PENDING_INSPECTION")
    locker = _make_locker(locker_id=locker_id, locker_status="MAINTENANCE")

    fake_db = _make_judge_session(admin, evaluation, loan, asset, locker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/admin/evaluations/{eval_id}/judge",
            headers=_bearer(admin),
            json={
                "is_approved": False,
                "rejection_reason": "Locker was actually empty",
            },
        )

    assert response.status_code == 204
    assert evaluation.is_approved is False
    assert evaluation.rejection_reason == "Locker was actually empty"
    assert loan.loan_status == "ACTIVE"
    assert asset.asset_status == "BORROWED"
    assert locker.locker_status == "AVAILABLE"
    assert fake_db.commit_calls == 1


def test_judge_rejected_return_reverts_to_completed_and_available(
    client_with_overrides,
):
    """is_approved=False on RETURN → loan COMPLETED, asset AVAILABLE, locker OCCUPIED."""

    admin = _make_admin()
    eval_id = uuid.uuid4()
    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    return_locker_id = uuid.uuid4()

    evaluation = _make_evaluation(
        evaluation_id=eval_id,
        loan_id=loan_id,
        evaluation_type="RETURN",
    )
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=uuid.uuid4(),
        return_locker_id=return_locker_id,
        loan_status="PENDING_INSPECTION",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="PENDING_INSPECTION")
    locker = _make_locker(locker_id=return_locker_id, locker_status="MAINTENANCE")

    fake_db = _make_judge_session(admin, evaluation, loan, asset, locker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/admin/evaluations/{eval_id}/judge",
            headers=_bearer(admin),
            json={"is_approved": False},
        )

    assert response.status_code == 204
    assert evaluation.is_approved is False
    assert loan.loan_status == "COMPLETED"
    assert loan.returned_at is not None
    assert asset.asset_status == "AVAILABLE"
    assert locker.locker_status == "OCCUPIED"
    assert fake_db.commit_calls == 1

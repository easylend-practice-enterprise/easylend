import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import security
from app.core.config import settings
from app.core.state_machine import LoanStateMachine
from app.core.websockets import manager
from app.db.models import LoanStatus, LockerStatus, UserStatus
from app.tests.conftest import _QueuedSession


def _make_student(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=kwargs.get("user_id", uuid.uuid4()),
        role_id=uuid.uuid4(),
        first_name="Student",
        last_name="Test",
        email="student@easylend.be",
        nfc_tag_id=kwargs.get("nfc_tag_id", security.hash_nfc_tag("NFC-E2E-001")),
        pin_hash=kwargs.get("pin_hash", security.get_pin_hash("123456")),
        failed_login_attempts=0,
        locked_until=None,
        status=UserStatus.ACTIVE,
        ban_reason=None,
        role=SimpleNamespace(role_name="Student"),
        accepted_privacy_policy=False,
    )


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        category_id=uuid.uuid4(),
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        name="Test Asset",
        aztec_code=kwargs.get("aztec_code", "AZT-E2E"),
        asset_status=kwargs.get("asset_status", "AVAILABLE"),
        is_deleted=False,
    )


def _make_locker(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        logical_number=1,
        locker_status=kwargs.get("locker_status", "AVAILABLE"),
    )


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        user_id=kwargs.get("user_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id", uuid.uuid4()),
        return_locker_id=None,
        loan_status=kwargs.get("loan_status", "RESERVED"),
    )


@pytest.fixture(autouse=True)
def mock_audit_loggers(monkeypatch):
    import app.api.v1.endpoints.auth as auth_endpoints
    import app.api.v1.endpoints.loans as loans_endpoints

    monkeypatch.setattr(auth_endpoints, "log_audit_event", AsyncMock())
    monkeypatch.setattr(loans_endpoints, "log_audit_event", AsyncMock())


@pytest.fixture(autouse=True)
def mock_hardware_manager(monkeypatch):
    class AlwaysConnectedDict(dict):
        def __contains__(self, key):
            return True

    monkeypatch.setattr(manager, "active_connections", AlwaysConnectedDict())
    monkeypatch.setattr(manager, "send_command", AsyncMock(return_value=True))


@pytest.mark.anyio
async def test_e2e_checkout_happy_path(client_with_overrides, monkeypatch):
    """
    E2E Integration Test for the Checkout Flow.
    Validates state transitions and DB queries across multiple endpoints.
    """
    # 1. Setup Data Models
    nfc_tag = "NFC-E2E-001"
    pin = "123456"
    aztec_code = "AZT-E2E-001"

    student = _make_student(
        nfc_tag_id=security.hash_nfc_tag(nfc_tag), pin_hash=security.get_pin_hash(pin)
    )
    kiosk = SimpleNamespace(kiosk_id=uuid.uuid4(), status="ONLINE")
    locker = _make_locker(kiosk_id=kiosk.kiosk_id, locker_status="OCCUPIED")
    asset = _make_asset(aztec_code=aztec_code, locker_id=locker.locker_id)
    loan = _make_loan(
        user_id=student.user_id,
        asset_id=asset.asset_id,
        checkout_locker_id=locker.locker_id,
        loan_status="RESERVED",
    )

    # Mock Vision microservice forwarder (used by PATCH /api/v1/update-model)
    import app.api.v1.endpoints.vision as vision_endpoints

    def _async_client_factory(*, timeout: float):  # noqa: ARG001
        class _CapturingClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(
                self, url: str, *, json: dict | None = None, headers: dict | None = None
            ):
                return SimpleNamespace(status_code=200, text="OK")

        return _CapturingClient()

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    # Fake database queue with the exact sequence of reads needed across the E2E flow
    fake_db = _QueuedSession(
        student,  # 1. POST /auth/nfc -> _get_active_user_by_nfc
        student,  # 2. POST /auth/pin -> _get_active_user_by_nfc (Step 1)
        student,  # 3. POST /auth/pin -> lock user row by user_id (Step 2)
        student,  # 4. POST /loans/checkout -> get_current_user
        0,  # 5. POST /loans/checkout -> count active loans
        asset,  # 6. POST /loans/checkout -> lock asset FOR UPDATE
        locker,  # 7. POST /loans/checkout -> lock locker FOR UPDATE
        student,  # 8. GET /loans/{loan_id}/status -> get_current_user
        loan,  # 9. GET /loans/{loan_id}/status -> _get_loan_or_404
    )

    with client_with_overrides(fake_db) as client:
        # 2. Login Flow
        nfc_response = client.post("/api/v1/auth/nfc", json={"nfc_tag_id": nfc_tag})
        assert nfc_response.status_code == 200

        pin_response = client.post(
            "/api/v1/auth/pin", json={"nfc_tag_id": nfc_tag, "pin": pin}
        )
        assert pin_response.status_code == 200
        token = pin_response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "e2e-checkout-key-1",
        }

        # 3. Checkout Flow
        checkout_response = client.post(
            "/api/v1/loans/checkout", json={"aztec_code": aztec_code}, headers=headers
        )
        assert checkout_response.status_code == 202
        checkout_data = checkout_response.json()
        assert checkout_data["loan_status"] == "RESERVED"
        loan_id = checkout_data["loan_id"]

        # Verify db state immediately after checkout
        assert asset.asset_status == "BORROWED"
        assert locker.locker_status == "OCCUPIED"

        from typing import cast

        cast(AsyncMock, manager.send_command).assert_called_with(
            str(kiosk.kiosk_id),
            {
                "action": "open_slot",
                "locker_id": locker.logical_number,
                "loan_id": str(loan_id),
                "evaluation_type": "CHECKOUT",
            },
        )

        # 5. AI Webhook
        webhook_response = client.patch(
            "/api/v1/update-model",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            json={
                "object_detection_url": "https://models.example.com/object.pt",
                "segmentation_url": "https://models.example.com/segmentation.pt",
            },
        )
        assert webhook_response.status_code == 200

        # 6. Simulate Vision Success
        # The Vision Service confirms locker empty, so the State Machine advances to ACTIVE
        LoanStateMachine.apply_transition(loan, asset, locker, LoanStatus.ACTIVE)
        asset.locker_id = None

        assert loan.loan_status == LoanStatus.ACTIVE
        assert asset.locker_id is None
        assert locker.locker_status == LockerStatus.AVAILABLE

        # 7. Polling Validation
        status_response = client.get(
            f"/api/v1/loans/{loan.loan_id}/status", headers=headers
        )
        assert status_response.status_code == 200
        assert status_response.json()["loan_status"] == "ACTIVE"

import asyncio
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.v1.endpoints import vision as vision_endpoints
from app.core.config import settings
from app.db.models import AIEvaluation
from app.tests.conftest import _FakeResult, _QueuedSession


def _vision_form_data(
    *, loan_id: uuid.UUID | None = None, evaluation_type: str
) -> dict:
    return {
        "loan_id": str(loan_id or uuid.uuid4()),
        "evaluation_type": evaluation_type,
    }


def _make_loan(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        loan_id=kwargs.get("loan_id", uuid.uuid4()),
        user_id=kwargs.get("user_id", uuid.uuid4()),
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id", uuid.uuid4()),
        return_locker_id=kwargs.get("return_locker_id"),
        loan_status=kwargs.get("loan_status", "RESERVED"),
    )


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        asset_status=kwargs.get("asset_status", "BORROWED"),
        locker_id=kwargs.get("locker_id"),
        is_deleted=kwargs.get("is_deleted", False),
    )


def _make_locker(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        logical_number=kwargs.get("logical_number", 1),
        locker_status=kwargs.get("locker_status", "OCCUPIED"),
    )


class _MockResponse:
    def __init__(self, status_code: int, payload: dict | list):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict | list:
        return self._payload


class _MockAsyncClient:
    def __init__(
        self,
        *,
        timeout: float,
        response: _MockResponse | None = None,
        error: Exception | None = None,
        captured: dict | None = None,
    ):
        self.timeout = timeout
        self._response = response
        self._error = error
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def post(self, url: str, *, headers: dict, files: dict):
        if self._captured is not None:
            if "urls" not in self._captured:
                self._captured["urls"] = []
            self._captured["urls"].append(url)
            self._captured["headers"] = headers
            self._captured["files"] = files

        if self._error is not None:
            raise self._error

        if self._response is None:
            raise AssertionError("Expected a mock response for post().")

        return self._response


class _ScalarResult(_FakeResult):
    def __init__(self, value):
        super().__init__(value)

    def scalar_one_or_none(self):
        return self._value


class _ConcurrentLoanLockState:
    def __init__(self, loan, asset, locker):
        self.loan = loan
        self.asset = asset
        self.locker = locker
        self.is_locked = False
        self.guard = threading.Lock()


class _ConcurrentLoanLockSession(_QueuedSession):
    """Session stub that simulates FOR UPDATE NOWAIT lock contention on Loan.

    In the refactored analyze_image, Phase 1 loads entities without locks.
    Phase 2 acquires FOR UPDATE locks immediately before DB mutations.
    Thread 1 gets the Phase 1 loan, runs AI (~30s), then in Phase 2 acquires
    the FOR UPDATE lock. Thread 2 hits NOWAIT contention on its Phase 2 lock
    attempt and gets a 409.
    """

    def __init__(self, state: _ConcurrentLoanLockState):
        super().__init__()
        self._state = state
        self._owns_lock = False
        self._phase = 0  # 0=phase1, 1=phase2

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute(self, query):
        query_str = str(query)
        is_phase2 = "FOR UPDATE" in query_str

        # Phase 2 FOR UPDATE on Loan: handle lock contention
        if is_phase2 and "FROM loans" in query_str:
            with self._state.guard:
                if self._state.is_locked:
                    raise OperationalError(
                        "could not obtain lock",
                        params=None,
                        orig=Exception("lock not available"),
                    )
                self._state.is_locked = True
                self._owns_lock = True

            # Keep the lock long enough for the competing request
            # to hit the NOWAIT conflict path.
            await asyncio.sleep(0.05)
            return _ScalarResult(self._state.loan)

        # Phase 2 FOR UPDATE on Asset
        if is_phase2 and "FROM assets" in query_str:
            return _ScalarResult(self._state.asset)

        # Phase 2 FOR UPDATE on Locker
        if is_phase2 and "FROM lockers" in query_str:
            return _ScalarResult(self._state.locker)

        # Phase 1: return entities without locks
        if "FROM loans" in query_str:
            return _ScalarResult(self._state.loan)

        if "FROM assets" in query_str:
            return _ScalarResult(self._state.asset)

        if "FROM lockers" in query_str:
            return _ScalarResult(self._state.locker)

        return _ScalarResult(None)

    async def commit(self):
        self.commit_calls += 1
        self._release_owner_lock_if_needed()

    async def rollback(self):
        self.rollback_calls += 1
        self._release_owner_lock_if_needed()

    def _release_owner_lock_if_needed(self) -> None:
        with self._state.guard:
            if self._owns_lock:
                self._state.is_locked = False
                self._owns_lock = False


def _mock_success_upstream(monkeypatch, payload: dict, captured: dict | None = None):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(200, payload.copy()),
            captured=captured,
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)


def _mock_common_vision_runtime(monkeypatch, tmp_path, fake_db=None):
    monkeypatch.setattr(vision_endpoints.settings, "VISION_SERVICE_URL", "http://vm2")
    monkeypatch.setattr(
        vision_endpoints.settings, "VISION_API_KEY", "vision-service-key"
    )
    monkeypatch.setattr(vision_endpoints.settings, "VISION_BOX_API_KEY", "device-key")
    send_command_mock = AsyncMock(return_value=True)
    audit_mock = AsyncMock()
    monkeypatch.setattr(vision_endpoints.manager, "send_command", send_command_mock)
    monkeypatch.setattr("app.api.v1.endpoints.vision.log_audit_event", audit_mock)
    monkeypatch.setattr(vision_endpoints, "UPLOAD_DIR", tmp_path)
    if fake_db is not None:
        _patch_session_factory(monkeypatch, fake_db)
    return send_command_mock, audit_mock


def _patch_session_factory(monkeypatch, fake_db):
    """Monkeypatch AsyncSessionLocal in the vision module to return the fake session.

    The refactored analyze_image uses ``async with AsyncSessionLocal() as db:``
    instead of ``Depends(get_db)``. This helper makes the factory callable
    return the given fake_db stub directly.
    """
    monkeypatch.setattr(vision_endpoints, "AsyncSessionLocal", lambda: fake_db)


def test_vision_analyze_success(monkeypatch, client_with_overrides, tmp_path):
    captured: dict = {}
    expected_payload = {
        "status": "success",
        "count": 1,
        "detections": [{"class_name": "laptop", "confidence": 0.98}],
        "locker_empty": False,
        "has_damage_detected": False,
    }

    # Mock UUID so we get a predictable photo_url in the test
    class MockUUID:
        hex = "1234567890abcdef1234567890abcdef"

    monkeypatch.setattr(vision_endpoints.uuid, "uuid4", lambda: MockUUID())
    _mock_success_upstream(monkeypatch, expected_payload, captured)

    loan_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    asset_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    checkout_locker_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _send_command_mock, _audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200

    response_json = response.json()
    assert response_json["status"] == expected_payload["status"]
    assert response_json["count"] == expected_payload["count"]
    # Verify the dynamically added photo_url based on our mocked UUID
    assert (
        response_json["photo_url"]
        == "/api/v1/images/1234567890abcdef1234567890abcdef.jpg"
    )

    assert set(captured["urls"]) == {"http://vm2/detect", "http://vm2/segment"}
    assert captured["headers"] == {"Authorization": "Bearer vision-service-key"}
    assert captured["files"]["file"] == ("sample.jpg", b"image-bytes", "image/jpeg")

    assert len(fake_db.added) == 1
    assert isinstance(fake_db.added[0], AIEvaluation)
    assert fake_db.added[0].loan_id == loan_id
    assert fake_db.added[0].evaluation_type == "CHECKOUT"
    assert fake_db.added[0].has_damage_detected is False


def test_checkout_success_branch_sets_active_and_green_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 0,
        "detections": [],
        "locker_empty": True,
        "has_damage_detected": False,
    }
    _mock_success_upstream(monkeypatch, payload)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED", locker_id=locker_id)
    locker = _make_locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=7,
        locker_status="AVAILABLE",
    )
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    send_command_mock, audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert loan.loan_status == "ACTIVE"
    assert getattr(loan, "borrowed_at", None) is not None
    assert asset.asset_status == "BORROWED"
    assert asset.locker_id is None
    assert locker.locker_status == "AVAILABLE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": 7, "color": "green"},
    )
    # There are now two audit calls: LOAN_CHECKOUT_CONFIRMED + VISION_EVALUATION_PROCESSED.
    audit_mock.assert_awaited()
    vision_call = next(
        c
        for c in audit_mock.call_args_list
        if c.kwargs.get("action_type") == "VISION_EVALUATION_PROCESSED"
    )
    assert vision_call is not None
    kwargs = vision_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "CHECKOUT"
    assert kwargs["payload"]["has_damage_detected"] is False

    assert len(fake_db.added) == 1
    eval_record = fake_db.added[0]
    assert eval_record.has_damage_detected is False
    assert eval_record.ai_confidence == 0.0
    assert eval_record.model_version == "yolo26-dual-model"


def test_vision_analyze_concurrent_requests_return_409(monkeypatch, tmp_path):
    payload = {
        "status": "success",
        "count": 0,
        "detections": [],
        "locker_empty": True,
        "has_damage_detected": False,
    }
    _mock_success_upstream(monkeypatch, payload)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED", locker_id=locker_id)
    locker = _make_locker(locker_id=locker_id, locker_status="OCCUPIED")
    state = _ConcurrentLoanLockState(loan, asset, locker)

    # Patch AsyncSessionLocal to return a fresh _ConcurrentLoanLockSession per call.
    # Each concurrent thread gets its own session, sharing the lock state.
    monkeypatch.setattr(
        vision_endpoints,
        "AsyncSessionLocal",
        lambda: _ConcurrentLoanLockSession(state),
    )
    _mock_common_vision_runtime(monkeypatch, tmp_path)

    from app.main import app

    responses = []
    errors = []
    start_barrier = threading.Barrier(2)

    def _send_once() -> None:
        try:
            with TestClient(app) as client:
                start_barrier.wait()
                response = client.post(
                    "/api/v1/vision/analyze",
                    headers={"X-Device-Token": "device-key"},
                    data=_vision_form_data(
                        loan_id=loan_id,
                        evaluation_type="CHECKOUT",
                    ),
                    files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
                )
                responses.append(response)
        except Exception as exc:  # pragma: no cover - defensive test guard
            errors.append(exc)

    thread_1 = threading.Thread(target=_send_once)
    thread_2 = threading.Thread(target=_send_once)
    thread_1.start()
    thread_2.start()
    thread_1.join(timeout=5)
    thread_2.join(timeout=5)

    assert not errors
    assert len(responses) == 2
    assert sorted([responses[0].status_code, responses[1].status_code]) == [200, 409]

    conflict_response = next(r for r in responses if r.status_code == 409)
    assert conflict_response.json()["detail"] == (
        "Vision evaluation is already processing for this loan. Please try again."
    )


def test_checkout_fraud_branch_sets_fraud_and_red_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 1,
        "detections": [{"class_name": "laptop", "confidence": 0.98}],
        "locker_empty": False,
        "has_damage_detected": False,
    }
    _mock_success_upstream(monkeypatch, payload)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locker = _make_locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=8,
        locker_status="AVAILABLE",
    )
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    send_command_mock, audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert loan.loan_status == "FRAUD_SUSPECTED"
    assert asset.asset_status == "AVAILABLE"
    assert asset.locker_id == locker_id
    assert locker.locker_status == "OCCUPIED"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": 8, "color": "red"},
    )
    # There are now two audit calls: LOAN_CHECKOUT_FRAUD + VISION_EVALUATION_PROCESSED.
    audit_mock.assert_awaited()
    vision_call = next(
        c
        for c in audit_mock.call_args_list
        if c.kwargs.get("action_type") == "VISION_EVALUATION_PROCESSED"
    )
    assert vision_call is not None
    kwargs = vision_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "CHECKOUT"
    assert kwargs["payload"]["has_damage_detected"] is False

    assert len(fake_db.added) == 1
    eval_record = fake_db.added[0]
    assert eval_record.has_damage_detected is False
    assert eval_record.ai_confidence == 0.98
    assert eval_record.model_version == "yolo26-dual-model"


def test_return_success_branch_sets_completed_and_green_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 0,
        "detections": [],
        "locker_empty": False,
        "has_damage_detected": False,
    }
    _mock_success_upstream(monkeypatch, payload)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    return_locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        return_locker_id=return_locker_id,
        loan_status="RETURNING",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locker = _make_locker(
        locker_id=return_locker_id,
        kiosk_id=kiosk_id,
        logical_number=9,
        locker_status="OCCUPIED",
    )
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    send_command_mock, audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="RETURN"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert loan.loan_status == "COMPLETED"
    assert getattr(loan, "returned_at", None) is not None
    assert asset.asset_status == "AVAILABLE"
    assert asset.locker_id == return_locker_id
    assert locker.locker_status == "OCCUPIED"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": 9, "color": "green"},
    )
    # There are now two audit calls: LOAN_RETURN_CONFIRMED + VISION_EVALUATION_PROCESSED.
    audit_mock.assert_awaited()
    vision_call = next(
        c
        for c in audit_mock.call_args_list
        if c.kwargs.get("action_type") == "VISION_EVALUATION_PROCESSED"
    )
    assert vision_call is not None
    kwargs = vision_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "RETURN"
    assert kwargs["payload"]["has_damage_detected"] is False

    assert len(fake_db.added) == 1
    eval_record = fake_db.added[0]
    assert eval_record.has_damage_detected is False
    assert eval_record.ai_confidence == 0.0
    assert eval_record.model_version == "yolo26-dual-model"


def test_return_damage_branch_sets_pending_inspection_and_orange_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 1,
        "detections": [{"class_name": "damage_screen", "confidence": 0.91}],
        "locker_empty": False,
        "has_damage_detected": True,
    }
    _mock_success_upstream(monkeypatch, payload)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    return_locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        return_locker_id=return_locker_id,
        loan_status="RETURNING",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locker = _make_locker(
        locker_id=return_locker_id,
        kiosk_id=kiosk_id,
        logical_number=10,
        locker_status="OCCUPIED",
    )
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    send_command_mock, audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="RETURN"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert loan.loan_status == "PENDING_INSPECTION"
    assert asset.asset_status == "PENDING_INSPECTION"
    assert asset.locker_id == return_locker_id
    assert locker.locker_status == "MAINTENANCE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": 10, "color": "orange"},
    )
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    kwargs = audit_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "RETURN"
    assert kwargs["payload"]["has_damage_detected"] is True

    assert len(fake_db.added) == 1
    eval_record = fake_db.added[0]
    assert eval_record.has_damage_detected is True
    assert eval_record.ai_confidence == 0.91
    assert eval_record.model_version == "yolo26-dual-model"


def test_vision_analyze_rejects_non_image_file(monkeypatch, client_with_overrides):
    def _async_client_factory(*, timeout: float):  # noqa: ARG001
        raise AssertionError("Upstream call must not happen for non-image uploads.")

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
            files={"file": ("sample.txt", b"not-an-image", "text/plain")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a JPEG/PNG/WebP image."


def test_vision_analyze_requires_valid_device_token(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            data=_vision_form_data(evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid device token."


@pytest.mark.parametrize("upstream_status", [401, 403])
def test_vision_analyze_maps_upstream_auth_errors_to_500(
    monkeypatch, client_with_overrides, upstream_status
):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(upstream_status, {"detail": "forbidden"}),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Vision AI authentication is misconfigured."


def test_vision_analyze_maps_upstream_503(monkeypatch, client_with_overrides):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(503, {"detail": "starting"}),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Vision AI service is temporarily unavailable."


def test_vision_analyze_maps_upstream_400_to_400(monkeypatch, client_with_overrides):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(400, {"detail": "invalid image"}),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded image is invalid or unsupported."


def test_vision_analyze_maps_unexpected_upstream_errors_to_502(
    monkeypatch, client_with_overrides
):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(500, {"detail": "error"}),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 502
    assert (
        response.json()["detail"]
        == "Vision AI service returned an unexpected response."
    )


def test_vision_analyze_maps_request_errors_to_503(monkeypatch, client_with_overrides):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            error=httpx.ConnectError("connection failed"),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Vision AI service is unavailable."


def test_vision_analyze_maps_invalid_json_to_502(monkeypatch, client_with_overrides):
    class _MockInvalidJsonResponse(_MockResponse):
        def json(self):
            raise ValueError("Invalid JSON")

    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockInvalidJsonResponse(200, {}),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 502
    assert (
        response.json()["detail"] == "Vision AI service returned invalid data format."
    )


def test_vision_analyze_maps_non_dict_json_to_502(monkeypatch, client_with_overrides):
    """Test that upstream returning a JSON array (list) instead of object is caught safely."""

    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            # Upstream incorrectly returns a list!
            response=_MockResponse(200, [{"unexpected": "list"}]),
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    checkout_locker_id = uuid.uuid4()
    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=checkout_locker_id,
    )
    asset = _make_asset(asset_id=asset_id)
    locker = _make_locker(locker_id=checkout_locker_id)
    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 502
    assert (
        response.json()["detail"] == "Vision AI service returned invalid data format."
    )


def test_vision_analyze_cleans_up_file_when_finalize_fails(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 0,
        "detections": [],
        "locker_empty": True,
        "has_damage_detected": False,
    }
    _mock_success_upstream(monkeypatch, payload)
    _mock_common_vision_runtime(monkeypatch, tmp_path)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locker = _make_locker(locker_id=locker_id)

    class _FailingCommitSession(_QueuedSession):
        async def commit(self):
            raise RuntimeError("commit failed")

    # Phase 1 (3) + Phase 2 lock acquisition (3)
    fake_db = _FailingCommitSession(loan, asset, locker, loan, asset, locker)
    _patch_session_factory(monkeypatch, fake_db)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to finalize vision evaluation."
    assert list(tmp_path.iterdir()) == []


def test_update_model_accepts_dual_model_urls(monkeypatch, client_with_overrides):
    """The update-model webhook must forward the payload to the Vision microservice."""

    def _async_client_factory(*, timeout: float):  # noqa: ARG001
        class _SuccessClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url: str, *, json: dict, headers: dict):
                assert url == "http://vm2/update-model"
                assert headers["Authorization"] == "Bearer vision-service-key"
                assert (
                    json["object_detection_url"]
                    == "https://models.example.com/object.pt"
                )
                assert (
                    json["segmentation_url"]
                    == "https://models.example.com/segmentation.pt"
                )
                response = _MockResponse(200, {"message": "ok"})
                return response

        return _SuccessClient()

    monkeypatch.setattr(vision_endpoints.settings, "VISION_SERVICE_URL", "http://vm2")
    monkeypatch.setattr(
        vision_endpoints.settings, "VISION_API_KEY", "vision-service-key"
    )
    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/update-model",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            json={
                "object_detection_url": "https://models.example.com/object.pt",
                "segmentation_url": "https://models.example.com/segmentation.pt",
            },
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Model update received successfully."


def test_update_model_accepts_single_model_url(monkeypatch, client_with_overrides):
    """Single-URL payload should be forwarded to the Vision microservice."""
    captured: dict = {}

    class _CapturingClient:
        def __init__(self, *, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        async def post(
            self, url: str, *, json: dict | None = None, headers: dict | None = None
        ):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return SimpleNamespace(status_code=200, text="OK")

    # Patch AsyncClient used by the vision webhook forwarder
    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _CapturingClient)
    monkeypatch.setattr(vision_endpoints.settings, "VISION_SERVICE_URL", "http://vm2")
    monkeypatch.setattr(
        vision_endpoints.settings, "VISION_API_KEY", "vision-service-key"
    )
    monkeypatch.setattr(vision_endpoints.settings, "VISION_BOX_API_KEY", "device-key")

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/update-model",
            headers={"X-Device-Token": vision_endpoints.settings.VISION_BOX_API_KEY},
            json={"object_detection_url": "https://models.example.com/object.pt"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Model update received successfully."
    assert captured["url"] == "http://vm2/update-model"
    assert captured["headers"] == {"Authorization": "Bearer vision-service-key"}
    # The API forwards the pydantic model_dump() which may include the
    # optional segmentation_url key with a None value. Assert on the
    # meaningful field and allow segmentation_url to be present as None.
    assert (
        captured["json"]["object_detection_url"]
        == "https://models.example.com/object.pt"
    )
    assert captured["json"].get("segmentation_url") is None


def test_checkout_ai_timeout_sets_pending_inspection_and_orange_led(
    monkeypatch, client_with_overrides, tmp_path
):
    """If the AI service times out during CHECKOUT, trigger the safe fallback."""

    # Mock the AI request to raise a timeout error
    async def mock_post(*args, **kwargs):
        raise httpx.RequestError("Mocked Timeout")

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locker = _make_locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=4,
        locker_status="AVAILABLE",
    )

    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    send_command_mock, audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    # 503 Service Unavailable is expected on AI failure
    assert response.status_code == 503
    assert loan.loan_status == "PENDING_INSPECTION"
    assert asset.asset_status == "PENDING_INSPECTION"
    assert asset.locker_id == locker_id
    assert locker.locker_status == "MAINTENANCE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "4", "color": "orange"},
    )


def test_return_ai_timeout_sets_pending_inspection_and_orange_led(
    monkeypatch, client_with_overrides, tmp_path
):
    """If the AI service times out during RETURN, trigger the safe fallback."""

    # Mock the AI request to raise a timeout error
    async def mock_post(*args, **kwargs):
        raise httpx.RequestError("Mocked Timeout")

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    return_locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        return_locker_id=return_locker_id,
        loan_status="RETURNING",
    )
    asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locker = _make_locker(
        locker_id=return_locker_id,
        kiosk_id=kiosk_id,
        logical_number=5,
        locker_status="OCCUPIED",
    )

    fake_db = _QueuedSession(loan, asset, locker, loan, asset, locker)
    send_command_mock, audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="RETURN"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 503
    assert loan.loan_status == "PENDING_INSPECTION"
    assert asset.asset_status == "PENDING_INSPECTION"
    assert locker.locker_status == "MAINTENANCE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "5", "color": "orange"},
    )


def test_checkout_ai_timeout_mutates_only_locked_phase_entities(
    monkeypatch, client_with_overrides, tmp_path
):
    """Fallback state mutation must target Phase 2 locked rows, not Phase 1 snapshots."""

    async def mock_post(*args, **kwargs):
        raise httpx.RequestError("Mocked Timeout")

    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)

    loan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    locker_id = uuid.uuid4()
    kiosk_id = uuid.uuid4()

    phase1_loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    phase1_asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    phase1_locker = _make_locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=7,
        locker_status="AVAILABLE",
    )

    locked_loan = _make_loan(
        loan_id=loan_id,
        asset_id=asset_id,
        checkout_locker_id=locker_id,
        loan_status="RESERVED",
    )
    locked_asset = _make_asset(asset_id=asset_id, asset_status="BORROWED")
    locked_locker = _make_locker(
        locker_id=locker_id,
        kiosk_id=kiosk_id,
        logical_number=7,
        locker_status="AVAILABLE",
    )

    fake_db = _QueuedSession(
        phase1_loan,
        phase1_asset,
        phase1_locker,
        locked_loan,
        locked_asset,
        locked_locker,
    )
    send_command_mock, _audit_mock = _mock_common_vision_runtime(
        monkeypatch, tmp_path, fake_db
    )

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 503

    # Phase 1 snapshots must remain untouched.
    assert phase1_loan.loan_status == "RESERVED"
    assert phase1_asset.asset_status == "BORROWED"
    assert phase1_asset.locker_id is None
    assert phase1_locker.locker_status == "AVAILABLE"

    # Locked Phase 2 rows receive the fallback mutation.
    assert locked_loan.loan_status == "PENDING_INSPECTION"
    assert locked_asset.asset_status == "PENDING_INSPECTION"
    assert locked_asset.locker_id == locker_id
    assert locked_locker.locker_status == "MAINTENANCE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "7", "color": "orange"},
    )

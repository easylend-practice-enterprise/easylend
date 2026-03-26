import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.v1.endpoints import vision as vision_endpoints
from app.core.config import settings
from app.tests.conftest import _QueuedSession


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
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        checkout_locker_id=kwargs.get("checkout_locker_id", uuid.uuid4()),
        return_locker_id=kwargs.get("return_locker_id"),
        loan_status=kwargs.get("loan_status", "RESERVED"),
    )


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        asset_status=kwargs.get("asset_status", "BORROWED"),
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
            self._captured["url"] = url
            self._captured["headers"] = headers
            self._captured["files"] = files

        if self._error is not None:
            raise self._error

        if self._response is None:
            raise AssertionError("Expected a mock response for post().")

        return self._response


def _mock_success_upstream(monkeypatch, payload: dict, captured: dict | None = None):
    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(200, payload.copy()),
            captured=captured,
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)


def _mock_common_vision_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(vision_endpoints.settings, "VISION_SERVICE_URL", "http://vm2")
    monkeypatch.setattr(
        vision_endpoints.settings, "VISION_API_KEY", "vision-service-key"
    )
    monkeypatch.setattr(vision_endpoints.settings, "VISION_BOX_API_KEY", "device-key")
    send_command_mock = AsyncMock(return_value=True)
    audit_mock = AsyncMock()
    monkeypatch.setattr(vision_endpoints.manager, "send_command", send_command_mock)
    monkeypatch.setattr(vision_endpoints, "log_audit_event", audit_mock)
    monkeypatch.setattr(vision_endpoints, "UPLOAD_DIR", tmp_path)
    return send_command_mock, audit_mock


def test_vision_analyze_success(monkeypatch, client_with_overrides, tmp_path):
    captured: dict = {}
    expected_payload = {
        "status": "success",
        "count": 1,
        "detections": [{"class_name": "laptop", "confidence": 0.98}],
    }

    # Mock UUID so we get a predictable photo_url in the test
    class MockUUID:
        hex = "1234567890abcdef1234567890abcdef"

    monkeypatch.setattr(vision_endpoints.uuid, "uuid4", lambda: MockUUID())
    _mock_success_upstream(monkeypatch, expected_payload, captured)
    _send_command_mock, _audit_mock = _mock_common_vision_runtime(monkeypatch, tmp_path)

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
    fake_db = _QueuedSession(loan, asset, locker)

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

    assert captured["url"] == "http://vm2/predict"
    assert captured["headers"] == {"Authorization": "Bearer vision-service-key"}
    assert captured["files"]["file"] == ("sample.jpg", b"image-bytes", "image/jpeg")


def test_checkout_success_branch_sets_active_and_green_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 0,
        "detections": [],
    }
    _mock_success_upstream(monkeypatch, payload)
    send_command_mock, audit_mock = _mock_common_vision_runtime(monkeypatch, tmp_path)

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
        logical_number=7,
        locker_status="AVAILABLE",
    )
    fake_db = _QueuedSession(loan, asset, locker)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert loan.loan_status == "ACTIVE"
    assert asset.asset_status == "BORROWED"
    assert locker.locker_status == "AVAILABLE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "7", "color": "green"},
    )
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    kwargs = audit_call.kwargs
    assert kwargs["action_type"] == "VISION_EVALUATION_PROCESSED"
    assert kwargs["payload"]["evaluation_type"] == "CHECKOUT"
    assert kwargs["payload"]["outcome"] == "ACTIVE"


def test_checkout_fraud_branch_sets_fraud_and_red_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 1,
        "detections": [{"class_name": "laptop", "confidence": 0.98}],
    }
    _mock_success_upstream(monkeypatch, payload)
    send_command_mock, audit_mock = _mock_common_vision_runtime(monkeypatch, tmp_path)

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
    fake_db = _QueuedSession(loan, asset, locker)

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
    assert locker.locker_status == "AVAILABLE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "8", "color": "red"},
    )
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    kwargs = audit_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "CHECKOUT"
    assert kwargs["payload"]["outcome"] == "FRAUD_SUSPECTED"


def test_return_success_branch_sets_completed_and_green_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 0,
        "detections": [],
    }
    _mock_success_upstream(monkeypatch, payload)
    send_command_mock, audit_mock = _mock_common_vision_runtime(monkeypatch, tmp_path)

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
    fake_db = _QueuedSession(loan, asset, locker)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
            data=_vision_form_data(loan_id=loan_id, evaluation_type="RETURN"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert loan.loan_status == "COMPLETED"
    assert asset.asset_status == "AVAILABLE"
    assert locker.locker_status == "AVAILABLE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "9", "color": "green"},
    )
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    kwargs = audit_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "RETURN"
    assert kwargs["payload"]["outcome"] == "COMPLETED"


def test_return_damage_branch_sets_pending_inspection_and_red_led(
    monkeypatch, client_with_overrides, tmp_path
):
    payload = {
        "status": "success",
        "count": 1,
        "detections": [{"class_name": "damage_screen", "confidence": 0.91}],
    }
    _mock_success_upstream(monkeypatch, payload)
    send_command_mock, audit_mock = _mock_common_vision_runtime(monkeypatch, tmp_path)

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
    fake_db = _QueuedSession(loan, asset, locker)

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
    assert locker.locker_status == "MAINTENANCE"

    send_command_mock.assert_awaited_once_with(
        str(kiosk_id),
        {"action": "set_led", "locker_id": "10", "color": "red"},
    )
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    kwargs = audit_call.kwargs
    assert kwargs["payload"]["evaluation_type"] == "RETURN"
    assert kwargs["payload"]["outcome"] == "PENDING_INSPECTION"


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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
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

    with client_with_overrides(_QueuedSession()) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            data=_vision_form_data(evaluation_type="CHECKOUT"),
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 502
    assert (
        response.json()["detail"] == "Vision AI service returned invalid data format."
    )

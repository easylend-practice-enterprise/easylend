import httpx
import pytest

from app.api.v1.endpoints import vision as vision_endpoints
from app.core.config import settings


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

    def _async_client_factory(*, timeout: float):
        return _MockAsyncClient(
            timeout=timeout,
            response=_MockResponse(200, expected_payload.copy()),
            captured=captured,
        )

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)
    monkeypatch.setattr(vision_endpoints.settings, "VISION_SERVICE_URL", "http://vm2")
    monkeypatch.setattr(
        vision_endpoints.settings, "VISION_API_KEY", "vision-service-key"
    )
    monkeypatch.setattr(vision_endpoints.settings, "VISION_BOX_API_KEY", "device-key")

    # Use a temporary upload directory so the test does not write to the real UPLOAD_DIR
    monkeypatch.setattr(vision_endpoints, "UPLOAD_DIR", tmp_path)

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": "device-key"},
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


def test_vision_analyze_rejects_non_image_file(monkeypatch, client_with_overrides):
    def _async_client_factory(*, timeout: float):  # noqa: ARG001
        raise AssertionError("Upstream call must not happen for non-image uploads.")

    monkeypatch.setattr(vision_endpoints.httpx, "AsyncClient", _async_client_factory)

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            files={"file": ("sample.txt", b"not-an-image", "text/plain")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must be a JPEG/PNG/WebP image."


def test_vision_analyze_requires_valid_device_token(client_with_overrides):
    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
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

    with client_with_overrides(None) as client:
        response = client.post(
            "/api/v1/vision/analyze",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            files={"file": ("sample.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 502
    assert (
        response.json()["detail"] == "Vision AI service returned invalid data format."
    )

import os
import secrets
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

# Ensure tests use a non-hardcoded token value for auth checks.
os.environ.setdefault("VISION_API_KEY", secrets.token_urlsafe(24))
# Skip expensive OpenVINO compilation during unit tests.
os.environ.setdefault("SKIP_MODEL_LOADING", "1")

import main
from main import app


class DummyModel:
    def predict(self, source, imgsz=640):
        # Return an empty results list so the prediction path runs without errors
        return []


VALID_TOKEN = os.environ["VISION_API_KEY"]
AUTH_HEADER = {"Authorization": f"Bearer {VALID_TOKEN}"}


@pytest.fixture
def client():
    """Provide a TestClient fixture with a context manager for clean lifespan events."""
    with TestClient(app) as c:
        yield c


def test_detect_requires_auth(client):
    """Test that the detect endpoint fails without an auth token."""
    response = client.post("/detect")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_detect_rejects_invalid_token(client):
    """Test that the detect endpoint rejects an invalid token."""
    response = client.post(
        "/detect", headers={"Authorization": "Bearer invalid-token-123"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API token"


def test_detect_valid_token_no_file(client):
    """Test that auth succeeds but request fails without a file payload."""
    response = client.post("/detect", headers=AUTH_HEADER)
    # 422 Unprocessable Entity = Auth succeeded, but no Pydantic/File payload found
    assert response.status_code == 422


def test_detect_rejects_non_image(client):
    """Test that the detect endpoint rejects non-image files."""
    # Ensure a model is present so the request proceeds past the model check
    main.model = DummyModel()
    response = client.post(
        "/detect",
        headers=AUTH_HEADER,
        files={"file": ("test.txt", BytesIO(b"not an image"), "text/plain")},
    )
    assert response.status_code == 400
    assert "File must be a JPEG/PNG/WebP image" in response.json()["detail"]


def test_detect_rejects_oversize(client, monkeypatch):
    """Test that the detect endpoint rejects images larger than MAX_UPLOAD_SIZE."""
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    # Ensure a model is present so the request proceeds past the model check
    main.model = DummyModel()
    big_bytes = b"A" * 11
    response = client.post(
        "/detect",
        headers=AUTH_HEADER,
        files={"file": ("big.jpg", BytesIO(big_bytes), "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Image too large (max 10 bytes)"


def test_detect_handles_corrupt_image(client):
    """Test that a corrupt image payload returns a 400 with a generic error."""
    # Ensure a model is present so the request proceeds past the model check
    main.model = DummyModel()
    response = client.post(
        "/detect",
        headers=AUTH_HEADER,
        files={"file": ("bad.jpg", BytesIO(b"not really an image"), "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Error processing image"


def test_update_model_requires_auth(client):
    """Test that the model update webhook requires authentication."""
    response = client.post(
        "/update-model", json={"object_detection_url": "https://roboflow.com/best.pt"}
    )
    assert response.status_code == 401


def test_update_model_rejects_http(client):
    """Test that the webhook rejects non-HTTPS URLs to prevent SSRF."""
    response = client.post(
        "/update-model",
        headers=AUTH_HEADER,
        json={"object_detection_url": "http://insecure-site.com/best.pt"},
    )
    assert response.status_code == 400
    assert "Invalid or unsafe model URL" in response.json()["detail"]


def test_update_model_rejects_empty_url(client):
    """Test that the webhook rejects an empty download URL."""
    response = client.post(
        "/update-model",
        headers=AUTH_HEADER,
        json={"object_detection_url": ""},
    )
    assert response.status_code == 400
    assert "Invalid or unsafe model URL" in response.json()["detail"]

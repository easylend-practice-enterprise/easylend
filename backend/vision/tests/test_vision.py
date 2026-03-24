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


def test_predict_requires_auth(client):
    """Test that the predict endpoint fails without an auth token."""
    response = client.post("/predict")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_predict_rejects_invalid_token(client):
    """Test that the predict endpoint rejects an invalid token."""
    response = client.post(
        "/predict", headers={"Authorization": "Bearer invalid-token-123"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API token"


def test_predict_valid_token_no_file(client):
    """Test that auth succeeds but request fails without a file payload."""
    response = client.post("/predict", headers=AUTH_HEADER)
    # 422 Unprocessable Entity = Auth gelukt, maar geen Pydantic/File payload gevonden
    assert response.status_code == 422


def test_predict_rejects_non_image(client):
    """Test that the predict endpoint rejects non-image files."""
    response = client.post(
        "/predict",
        headers=AUTH_HEADER,
        files={"file": ("test.txt", BytesIO(b"not an image"), "text/plain")},
    )
    assert response.status_code == 400
    assert "File must be a JPEG/PNG/WebP image" in response.json()["detail"]


def test_predict_rejects_oversize(client, monkeypatch):
    """Test that the predict endpoint rejects images larger than MAX_UPLOAD_SIZE."""
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    # Ensure a model is present so the request proceeds past the model check
    main.model = DummyModel()
    big_bytes = b"A" * 11
    response = client.post(
        "/predict",
        headers=AUTH_HEADER,
        files={"file": ("big.jpg", BytesIO(big_bytes), "image/jpeg")},
    )
    assert response.status_code == 400
    # The app wraps internal failures with a generic error message.
    assert response.json()["detail"] == "Error processing image"


def test_predict_handles_corrupt_image(client):
    """Test that a corrupt image payload returns a 400 with a generic error."""
    # Send something with an image content-type but invalid bytes
    # Ensure a model is present so the request proceeds past the model check
    main.model = DummyModel()
    response = client.post(
        "/predict",
        headers=AUTH_HEADER,
        files={"file": ("bad.jpg", BytesIO(b"not really an image"), "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Error processing image"


def test_update_model_requires_auth(client):
    """Test that the model update webhook requires authentication."""
    response = client.post(
        "/update-model", json={"download_url": "https://roboflow.com/best.pt"}
    )
    assert response.status_code == 401


def test_update_model_rejects_http(client):
    """Test that the webhook rejects non-HTTPS URLs to prevent SSRF."""
    response = client.post(
        "/update-model",
        headers=AUTH_HEADER,
        json={"download_url": "http://insecure-site.com/best.pt"},
    )
    assert response.status_code == 400
    assert "Invalid or unsafe model URL" in response.json()["detail"]


def test_update_model_rejects_empty_url(client):
    """Test that the webhook rejects an empty download URL."""
    response = client.post(
        "/update-model",
        headers=AUTH_HEADER,
        json={"download_url": ""},
    )
    assert response.status_code == 400
    assert "Invalid or unsafe model URL" in response.json()["detail"]

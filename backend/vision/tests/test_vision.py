import os
import secrets

import pytest
from fastapi.testclient import TestClient

from main import app

# Ensure tests use a non-hardcoded token value for auth checks.
os.environ.setdefault("VISION_API_KEY", secrets.token_urlsafe(24))
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
    assert "Only HTTPS URLs are allowed" in response.json()["detail"]


def test_update_model_rejects_empty_url(client):
    """Test that the webhook rejects an empty download URL."""
    response = client.post(
        "/update-model",
        headers=AUTH_HEADER,
        json={"download_url": ""},
    )
    assert response.status_code == 400
    assert "Only HTTPS URLs are allowed" in response.json()["detail"]

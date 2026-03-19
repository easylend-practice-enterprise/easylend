from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import verify_simulation_token, verify_vision_box_token
from app.core.config import settings


def _build_test_client() -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/test")

    @router.get("/vision", dependencies=[Depends(verify_vision_box_token)])
    async def vision_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/simulation", dependencies=[Depends(verify_simulation_token)])
    async def simulation_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return TestClient(app)


def test_verify_vision_box_token_missing_header_returns_422(monkeypatch):
    monkeypatch.setattr(settings, "VISION_BOX_API_KEY", "vision-secret-token")
    client = _build_test_client()

    response = client.get("/test/vision")

    assert response.status_code == 422


def test_verify_vision_box_token_invalid_header_returns_401(monkeypatch):
    monkeypatch.setattr(settings, "VISION_BOX_API_KEY", "vision-secret-token")
    client = _build_test_client()

    response = client.get(
        "/test/vision",
        headers={"X-Device-Token": "wrong-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid device token."}


def test_verify_vision_box_token_valid_header_returns_200(monkeypatch):
    monkeypatch.setattr(settings, "VISION_BOX_API_KEY", "vision-secret-token")
    client = _build_test_client()

    response = client.get(
        "/test/vision",
        headers={"X-Device-Token": "vision-secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_simulation_token_missing_header_returns_422(monkeypatch):
    monkeypatch.setattr(settings, "SIMULATION_API_KEY", "simulation-secret-token")
    client = _build_test_client()

    response = client.get("/test/simulation")

    assert response.status_code == 422


def test_verify_simulation_token_invalid_header_returns_401(monkeypatch):
    monkeypatch.setattr(settings, "SIMULATION_API_KEY", "simulation-secret-token")
    client = _build_test_client()

    response = client.get(
        "/test/simulation",
        headers={"X-Device-Token": "wrong-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid device token."}


def test_verify_simulation_token_valid_header_returns_200(monkeypatch):
    monkeypatch.setattr(settings, "SIMULATION_API_KEY", "simulation-secret-token")
    client = _build_test_client()

    response = client.get(
        "/test/simulation",
        headers={"X-Device-Token": "simulation-secret-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

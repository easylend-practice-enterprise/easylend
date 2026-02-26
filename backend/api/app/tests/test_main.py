from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Welcome to the EasyLend API!",
        "docs_url": "/docs",
    }


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "components": {"api": "ok"}}

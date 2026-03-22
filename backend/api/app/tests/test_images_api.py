from app.api.v1.endpoints import images
from app.tests.conftest import FakeAsyncSession, _bearer, _make_admin


def test_get_image_success(client_with_overrides, monkeypatch, tmp_path):
    # 1. Mock de UPLOAD_DIR naar een tijdelijke map die na de test verdwijnt
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path)

    # 2. Maak een nep-foto aan in die tijdelijke map
    test_file = tmp_path / "test_photo.jpg"
    test_file.write_bytes(b"fake-image-bytes")

    # 3. Voer het request uit (client_with_overrides logt ons automatisch in als admin)
    admin = _make_admin()
    fake_db = FakeAsyncSession(admin)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/images/test_photo.jpg", headers=_bearer(admin))

    # 4. Controleer of de file netjes geserveerd wordt
    assert response.status_code == 200
    assert response.content == b"fake-image-bytes"
    assert response.headers["content-type"] == "image/jpeg"


def test_get_image_path_traversal_blocked(client_with_overrides, monkeypatch, tmp_path):
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path)

    admin = _make_admin()
    fake_db = FakeAsyncSession(admin)
    with client_with_overrides(fake_db) as client:
        # We proberen stiekem uit de map te breken met ../
        response = client.get(
            "/api/v1/images/..%2F..%2Fetc%2Fpasswd", headers=_bearer(admin)
        )

    # FastAPI's router snijdt gevaarlijke paden zelf al af voordat het bij ons endpoint komt.
    # Verwacht gedrag van het framework is 404 Not Found.
    assert response.status_code == 404


def test_get_image_not_found(client_with_overrides, monkeypatch, tmp_path):
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path)

    admin = _make_admin()
    fake_db = FakeAsyncSession(admin)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/images/doesnotexist.jpg", headers=_bearer(admin))

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"

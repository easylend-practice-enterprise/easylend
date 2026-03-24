from app.api.v1.endpoints import images
from app.tests.conftest import FakeAsyncSession, _bearer, _make_admin

# Gebruik een geldige UUID-bestandsnaam voor de test, want onze API eist dit nu!
VALID_TEST_FILENAME = "1234567890abcdef1234567890abcdef.jpg"


def test_get_image_success(client_with_overrides, monkeypatch, tmp_path):
    # 1. Mock the UPLOAD_DIR to a temporary directory that is removed after the test
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path)

    # 2. Create a fake photo file in that temporary directory
    test_file = tmp_path / VALID_TEST_FILENAME
    test_file.write_bytes(b"fake-image-bytes")

    # 3. Perform the request (client_with_overrides automatically logs us in as admin)
    admin = _make_admin()
    fake_db = FakeAsyncSession(admin)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/images/{VALID_TEST_FILENAME}", headers=_bearer(admin)
        )

    # 4. Verify the file is served correctly
    assert response.status_code == 200
    assert response.content == b"fake-image-bytes"
    assert response.headers["content-type"] == "image/jpeg"


def test_get_image_path_traversal_blocked(client_with_overrides, monkeypatch, tmp_path):
    """
    Test that path traversal attempts are rejected.
    FastAPI's router strictly requires a flat {filename} and rejects slashes.
    HTTP clients also normalize '..' out of URLs.
    Therefore, the expected and most secure behavior is a 404 Not Found.
    """
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path)

    admin = _make_admin()
    fake_db = FakeAsyncSession(admin)
    with client_with_overrides(fake_db) as client:
        # Attempt URL-encoded path traversal (e.g., moving up directories)
        response_encoded = client.get(
            "/api/v1/images/..%2F..%2Fetc%2Fpasswd", headers=_bearer(admin)
        )
        # Try literal dots (attempt to escape the directory)
        response_dots = client.get("/api/v1/images/..", headers=_bearer(admin))

    # The framework should block these before they reach our code.
    assert response_encoded.status_code == 404
    assert response_dots.status_code == 404


def test_get_image_not_found(client_with_overrides, monkeypatch, tmp_path):
    monkeypatch.setattr(images, "UPLOAD_DIR", tmp_path)

    admin = _make_admin()
    fake_db = FakeAsyncSession(admin)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/images/doesnotexist.jpg", headers=_bearer(admin))

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"

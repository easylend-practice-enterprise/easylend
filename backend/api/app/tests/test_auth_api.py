import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.v1.endpoints import auth as auth_endpoints
from app.core import security
from app.db.database import get_db
from app.main import app


class FakeExecuteResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class FakeAsyncSession:
    def __init__(self, user):
        self.user = user
        self.commit_calls = 0

    async def execute(self, query):  # noqa: ARG002
        return FakeExecuteResult(self.user)

    async def commit(self):
        self.commit_calls += 1


def _build_user(*, pin: str = "123456"):
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        nfc_tag_id="NFC-001",
        pin_hash=security.get_pin_hash(pin),
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        role=SimpleNamespace(role_name="Admin"),
    )


def _build_client_with_overrides(fake_db):
    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_refresh_endpoint_is_single_use(monkeypatch):
    valid_refresh_tokens: set[tuple[str, str]] = set()

    async def _mock_store_refresh_token(
        user_id: str, jti: str, expires_in_seconds: int
    ):  # noqa: ARG001
        valid_refresh_tokens.add((user_id, jti))

    async def _mock_revoke_refresh_token(user_id: str, jti: str) -> bool:
        key = (user_id, jti)
        if key not in valid_refresh_tokens:
            return False
        valid_refresh_tokens.remove(key)
        return True

    monkeypatch.setattr(
        auth_endpoints, "store_refresh_token", _mock_store_refresh_token
    )
    monkeypatch.setattr(
        auth_endpoints, "revoke_refresh_token", _mock_revoke_refresh_token
    )

    user = _build_user()
    fake_db = FakeAsyncSession(user)

    refresh_token = security.create_refresh_token(user.user_id)
    refresh_payload = security.verify_refresh_token(refresh_token)
    valid_refresh_tokens.add((str(refresh_payload.sub), str(refresh_payload.jti)))

    try:
        with _build_client_with_overrides(fake_db) as client:
            first_response = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert first_response.status_code == 200
            assert "access_token" in first_response.json()
            assert "refresh_token" in first_response.json()

            second_response = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert second_response.status_code == 401
            assert second_response.json()["detail"] == "Ongeldige refresh token."
    finally:
        app.dependency_overrides.clear()


def test_logout_revokes_refresh_token(monkeypatch):
    valid_refresh_tokens: set[tuple[str, str]] = set()

    async def _mock_store_refresh_token(
        user_id: str, jti: str, expires_in_seconds: int
    ):  # noqa: ARG001
        valid_refresh_tokens.add((user_id, jti))

    async def _mock_revoke_refresh_token(user_id: str, jti: str) -> bool:
        key = (user_id, jti)
        if key not in valid_refresh_tokens:
            return False
        valid_refresh_tokens.remove(key)
        return True

    monkeypatch.setattr(
        auth_endpoints, "store_refresh_token", _mock_store_refresh_token
    )
    monkeypatch.setattr(
        auth_endpoints, "revoke_refresh_token", _mock_revoke_refresh_token
    )

    user = _build_user()
    fake_db = FakeAsyncSession(user)

    refresh_token = security.create_refresh_token(user.user_id)
    refresh_payload = security.verify_refresh_token(refresh_token)
    valid_refresh_tokens.add((str(refresh_payload.sub), str(refresh_payload.jti)))

    try:
        with _build_client_with_overrides(fake_db) as client:
            logout_response = client.post(
                "/api/v1/auth/logout", json={"refresh_token": refresh_token}
            )
            assert logout_response.status_code == 200
            assert logout_response.json()["detail"] == "Succesvol uitgelogd."

            refresh_response = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert refresh_response.status_code == 401
            assert refresh_response.json()["detail"] == "Ongeldige refresh token."
    finally:
        app.dependency_overrides.clear()


def test_pin_endpoint_lockout_after_five_failed_attempts(monkeypatch):
    async def _mock_store_refresh_token(
        user_id: str, jti: str, expires_in_seconds: int
    ):  # noqa: ARG001
        return None

    async def _mock_revoke_refresh_token(user_id: str, jti: str) -> bool:  # noqa: ARG001
        return False

    monkeypatch.setattr(
        auth_endpoints, "store_refresh_token", _mock_store_refresh_token
    )
    monkeypatch.setattr(
        auth_endpoints, "revoke_refresh_token", _mock_revoke_refresh_token
    )

    user = _build_user(pin="123456")
    fake_db = FakeAsyncSession(user)

    payload = {"nfc_tag_id": user.nfc_tag_id, "pin": "000000"}

    try:
        with _build_client_with_overrides(fake_db) as client:
            for _ in range(5):
                response = client.post("/api/v1/auth/pin", json=payload)
                assert response.status_code == 401
                assert response.json()["detail"] == "Ongeldige PIN."

            # Na 5 fouten wordt het account gelockt; de volgende poging faalt op accountstatus.
            locked_response = client.post("/api/v1/auth/pin", json=payload)
            assert locked_response.status_code == 401
            assert (
                locked_response.json()["detail"]
                == "Ongeldige NFC badge of accountstatus."
            )
            assert user.locked_until is not None
            assert user.locked_until > datetime.now(UTC)
    finally:
        app.dependency_overrides.clear()

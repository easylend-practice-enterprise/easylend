from datetime import UTC, datetime
from unittest.mock import AsyncMock

from redis.exceptions import RedisError

from app.api.v1.endpoints import auth as auth_endpoints
from app.core import security
from app.tests.conftest import FakeAsyncSession


def test_refresh_endpoint_is_single_use(monkeypatch, build_user, client_with_overrides):
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

    user = build_user()
    fake_db = FakeAsyncSession(user)

    refresh_token = security.create_refresh_token(user.user_id)
    refresh_payload = security.verify_refresh_token(refresh_token)
    valid_refresh_tokens.add((str(refresh_payload.sub), str(refresh_payload.jti)))

    with client_with_overrides(fake_db) as client:
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
        assert second_response.json()["detail"] == "Invalid refresh token."


def test_logout_revokes_refresh_token(monkeypatch, build_user, client_with_overrides):
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

    user = build_user()
    fake_db = FakeAsyncSession(user)

    refresh_token = security.create_refresh_token(user.user_id)
    refresh_payload = security.verify_refresh_token(refresh_token)
    valid_refresh_tokens.add((str(refresh_payload.sub), str(refresh_payload.jti)))

    with client_with_overrides(fake_db) as client:
        logout_response = client.post(
            "/api/v1/auth/logout", json={"refresh_token": refresh_token}
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["detail"] == "Successfully logged out."

        refresh_response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert refresh_response.status_code == 401
        assert refresh_response.json()["detail"] == "Invalid refresh token."


def test_pin_endpoint_lockout_after_five_failed_attempts(
    monkeypatch, build_user, client_with_overrides
):
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
    monkeypatch.setattr(auth_endpoints, "log_audit_event", AsyncMock())

    user = build_user(pin="123456")
    fake_db = FakeAsyncSession(user)

    payload = {"nfc_tag_id": user.nfc_tag_id, "pin": "000000"}

    with client_with_overrides(fake_db) as client:
        for remaining in [4, 3, 2, 1]:
            response = client.post("/api/v1/auth/pin", json=payload)
            assert response.status_code == 401
            assert (
                response.json()["detail"]
                == f"Incorrect PIN. {remaining} attempts remaining."
            )

        # Fifth failed attempt applies lockout immediately.
        lock_response = client.post("/api/v1/auth/pin", json=payload)
        assert lock_response.status_code == 401
        assert lock_response.json()["detail"] == "Account is locked. Try again later."

        # After 5 failures the account is locked; the next attempt fails on account status.
        locked_response = client.post("/api/v1/auth/pin", json=payload)
        assert locked_response.status_code == 401
        assert (
            locked_response.json()["detail"] == "Invalid NFC badge or account status."
        )
        assert user.locked_until is not None
        assert user.locked_until > datetime.now(UTC)


def test_nfc_endpoint_returns_200_for_known_badge(build_user, client_with_overrides):
    user = build_user()
    fake_db = FakeAsyncSession(user)

    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/auth/nfc", json={"nfc_tag_id": user.nfc_tag_id})

    assert response.status_code == 200
    assert response.json()["detail"] == "NFC badge recognized. Enter PIN."


def test_nfc_endpoint_returns_401_for_unknown_badge(client_with_overrides):
    fake_db = FakeAsyncSession(None)

    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/auth/nfc", json={"nfc_tag_id": "UNKNOWN"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid NFC badge or account status."


def test_pin_endpoint_returns_503_when_redis_store_fails(
    monkeypatch, build_user, client_with_overrides
):
    async def _mock_store_refresh_token(
        user_id: str, jti: str, expires_in_seconds: int
    ):  # noqa: ARG001
        raise RedisError("redis down")

    monkeypatch.setattr(
        auth_endpoints, "store_refresh_token", _mock_store_refresh_token
    )
    monkeypatch.setattr(auth_endpoints, "log_audit_event", AsyncMock())

    user = build_user(pin="123456")
    fake_db = FakeAsyncSession(user)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/auth/pin",
            json={"nfc_tag_id": user.nfc_tag_id, "pin": "123456"},
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Authentication service is temporarily unavailable. Please try again later."
    )


def test_refresh_endpoint_returns_503_when_redis_revoke_fails(
    monkeypatch, build_user, client_with_overrides
):
    async def _mock_revoke_refresh_token(user_id: str, jti: str) -> bool:  # noqa: ARG001
        raise RedisError("redis down")

    monkeypatch.setattr(
        auth_endpoints, "revoke_refresh_token", _mock_revoke_refresh_token
    )

    user = build_user()
    fake_db = FakeAsyncSession(user)
    refresh_token = security.create_refresh_token(user.user_id)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"] == "Temporary service issue. Please try again later."
    )


def test_logout_endpoint_returns_503_when_redis_revoke_fails(
    monkeypatch, build_user, client_with_overrides
):
    async def _mock_revoke_refresh_token(user_id: str, jti: str) -> bool:  # noqa: ARG001
        raise RedisError("redis down")

    monkeypatch.setattr(
        auth_endpoints, "revoke_refresh_token", _mock_revoke_refresh_token
    )

    user = build_user()
    fake_db = FakeAsyncSession(user)
    refresh_token = security.create_refresh_token(user.user_id)

    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/auth/logout", json={"refresh_token": refresh_token}
        )

    assert response.status_code == 503
    assert (
        response.json()["detail"] == "Temporary service issue. Please try again later."
    )

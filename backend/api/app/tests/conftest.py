import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def build_user():
    return _build_user


@pytest.fixture
def client_with_overrides():
    def _build(fake_db):
        async def _override_get_db():
            yield fake_db

        app.dependency_overrides[get_db] = _override_get_db
        return TestClient(app)

    yield _build
    app.dependency_overrides.clear()

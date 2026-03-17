import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.db.database import get_db
from app.main import app


class _FakeResult:
    """
    Unified result stub.

    Supports both call patterns used in users.py:
    - result.scalar_one_or_none()   (single-row queries)
    - result.scalars().all()        (list queries in list_users)
    """

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value] if self._value is not None else []


class _QueuedSession:
    """
    Fake async DB session that returns pre-queued results in FIFO order.

    Each call to execute() pops the next value from the queue and wraps it
    in a _FakeResult. This lets us mock the exact sequence of DB calls made
    by each endpoint without caring about the query contents.

    Also tracks add() and commit() calls for assertion in tests.
    """

    def __init__(self, *results):
        self._queue = list(results)
        self.added: list = []
        self.commit_calls: int = 0
        self.rollback_calls: int = 0

    async def execute(self, _query):  # noqa: ARG002
        value = self._queue.pop(0) if self._queue else None
        return _FakeResult(value)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def refresh(self, obj):
        import uuid

        # Simuleer de database: genereer een UUID voor lege Primary Keys
        for pk_field in ["category_id", "kiosk_id", "locker_id", "asset_id"]:
            if hasattr(obj, pk_field) and getattr(obj, pk_field) is None:
                setattr(obj, pk_field, uuid.uuid4())
        # Simuleer de database: vul default waardes in voor Assets
        if hasattr(obj, "is_deleted") and getattr(obj, "is_deleted") is None:
            setattr(obj, "is_deleted", False)

    def add(self, obj):
        self.added.append(obj)


def _make_admin() -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Admin",
        last_name="Gebruiker",
        email="admin@easylend.be",
        nfc_tag_id="NFC-ADMIN-001",
        pin_hash=security.get_pin_hash("1234"),
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        role=SimpleNamespace(role_name="Admin"),
    )


def _make_medewerker() -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Jan",
        last_name="Medewerker",
        email="jan@easylend.be",
        nfc_tag_id="NFC-MEW-001",
        pin_hash=security.get_pin_hash("1234"),
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        role=SimpleNamespace(role_name="Medewerker"),
    )


def _bearer(user: SimpleNamespace) -> dict:
    """Generate a valid Authorization header with a real JWT for the given user."""
    token = security.create_access_token(user_id=user.user_id, role=user.role.role_name)
    return {"Authorization": f"Bearer {token}"}


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

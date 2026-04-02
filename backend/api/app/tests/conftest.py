import os

# Ensure the application picks up the test environment before importing
# any app modules that construct global resources (like the Redis client
# or DB engine). This prevents background workers or transports from
# starting during pytest runs.
os.environ.setdefault("ENVIRONMENT", "test")

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.db.redis as _redis_mod


# During tests, replace the real async Redis client with a lightweight
# fake to avoid the real client's background transport tasks which can
# raise "Future exception was never retrieved" warnings during pytest
# teardown. Apply the fake before importing `app.main` so modules that
# import the module-level `redis_client` will see the fake instance.
class _GlobalFakeRedis:
    async def ping(self):
        return True

    async def setex(self, *a, **kw):  # noqa: ARG002
        return None

    async def set(self, *a, **kw):  # noqa: ARG002
        return True

    async def exists(self, *a, **kw):  # noqa: ARG002
        return 0

    async def delete(self, *a, **kw):  # noqa: ARG002
        return 0

    async def scan(self, cursor, match=None):
        return (0, [])

    async def incr(self, key: str):  # noqa: ARG002
        # Rate-limit: always return 1 so requests are always allowed in tests
        return 1

    async def expire(self, key: str, seconds: int):  # noqa: ARG002
        return True

    async def aclose(self):
        return None

    def pipeline(self):
        return _FakePipeline()


class _FakePipeline:
    """Minimal pipeline stub for rate-limit tests."""

    def __init__(self):
        self._commands: list[tuple[str, list, dict]] = []

    def incr(self, key: str):
        self._commands.append(("incr", [key], {}))
        return self

    def expire(self, key: str, seconds: int):
        self._commands.append(("expire", [key, seconds], {}))
        return self

    async def execute(self):
        # Simulate: return [1] for first incr, True for expire
        results = []
        for cmd, args, _ in self._commands:
            if cmd == "incr":
                results.append(1)  # count starts at 1 — well under any limit
            elif cmd == "expire":
                results.append(True)
        self._commands.clear()
        return results


_redis_mod.redis_client = _GlobalFakeRedis()

# The application-level imports that reference `app` and `get_db` are
# performed inside the fixtures and helper functions below so that the
# Redis fake is installed before the application and its modules are
# imported by pytest. This keeps runtime behaviour correct while avoiding
# top-level import-order violations.


class _FakeResult:
    """
    Unified result stub.

    Supports call patterns used throughout the codebase:
    - result.scalar_one_or_none()   (single-row queries)
    - result.scalar_one()           (count queries)
    - result.scalars().all()        (list queries in list_users)
    """

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
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

    async def flush(self):
        # No-op for tests; present to mirror AsyncSession interface.
        return None

    async def refresh(self, obj):
        # Simulate the database: generate a UUID for empty Primary Keys
        for pk_field in [
            "category_id",
            "kiosk_id",
            "locker_id",
            "asset_id",
            "loan_id",
            "audit_id",
        ]:
            if hasattr(obj, pk_field) and getattr(obj, pk_field) is None:
                setattr(obj, pk_field, uuid.uuid4())
        # Simulate the database: set default values for Assets
        if hasattr(obj, "is_deleted") and getattr(obj, "is_deleted") is None:
            setattr(obj, "is_deleted", False)
        # Simulate the database: set default values for User status
        if hasattr(obj, "status") and getattr(obj, "status") is None:
            from app.db.models import UserStatus

            setattr(obj, "status", UserStatus.ACTIVE)

    def add(self, obj):
        self.added.append(obj)


def _make_admin() -> SimpleNamespace:
    from app.core import security
    from app.db.models import UserStatus

    return SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Admin",
        last_name="User",
        email="admin@easylend.be",
        nfc_tag_id="NFC-ADMIN-001",
        pin_hash=security.get_pin_hash("1234"),
        failed_login_attempts=0,
        locked_until=None,
        status=UserStatus.ACTIVE,
        ban_reason=None,
        accepted_privacy_policy=False,
        role=SimpleNamespace(role_name="Admin"),
    )


def _make_medewerker() -> SimpleNamespace:
    from app.core import security
    from app.db.models import UserStatus

    return SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Jan",
        last_name="Staff",
        email="jan@easylend.be",
        nfc_tag_id="NFC-MEW-001",
        pin_hash=security.get_pin_hash("1234"),
        failed_login_attempts=0,
        locked_until=None,
        status=UserStatus.ACTIVE,
        ban_reason=None,
        accepted_privacy_policy=False,
        role=SimpleNamespace(role_name="Staff"),
    )


def _bearer(user: SimpleNamespace) -> dict:
    """Generate a valid Authorization header with a real JWT for the given user."""
    from app.core import security

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
    from app.core import security
    from app.db.models import UserStatus

    return SimpleNamespace(
        user_id=uuid.uuid4(),
        nfc_tag_id="NFC-001",
        pin_hash=security.get_pin_hash(pin),
        failed_login_attempts=0,
        locked_until=None,
        status=UserStatus.ACTIVE,
        accepted_privacy_policy=False,
        role=SimpleNamespace(role_name="Admin"),
    )


@pytest.fixture
def build_user():
    return _build_user


@pytest.fixture
def client_with_overrides():
    def _build(fake_db):
        from app.db.database import get_db
        from app.main import app

        async def _override_get_db():
            yield fake_db

        app.dependency_overrides[get_db] = _override_get_db
        return TestClient(app)

    yield _build
    from app.main import app

    app.dependency_overrides.clear()

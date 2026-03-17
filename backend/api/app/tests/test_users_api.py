import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.core import security

# ─────────────────────────── Local test helpers ───────────────────────────────


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

    async def execute(self, _query):  # noqa: ARG002
        value = self._queue.pop(0) if self._queue else None
        return _FakeResult(value)

    async def commit(self):
        self.commit_calls += 1

    def add(self, obj):
        self.added.append(obj)


# ─────────────────────────── User factories ───────────────────────────────────


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


# ─────────────────────────── 1. Unauthenticated → 401 ────────────────────────
# No Authorization header -> auth dependency raises 401 before any DB call.


def test_get_me_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_list_users_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/users")
    assert response.status_code == 401


def test_get_user_by_id_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert response.status_code == 401


def test_create_user_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.post("/api/v1/users", json={})
    assert response.status_code == 401


def test_update_user_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.patch(f"/api/v1/users/{uuid.uuid4()}", json={})
    assert response.status_code == 401


def test_update_user_nfc_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.patch(
            f"/api/v1/users/{uuid.uuid4()}/nfc",
            json={"nfc_tag_id": "NFC-001"},
        )
    assert response.status_code == 401


# ─────────────────────────── 2. Non-admin role → 403 ─────────────────────────
# Valid JWT, wrong role → get_current_admin raises 403 after one DB execute
# (get_current_user fetches the user, get_current_admin checks role_name).


def test_list_users_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/users", headers=_bearer(medewerker))
    assert response.status_code == 403


def test_get_user_by_id_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/users/{uuid.uuid4()}", headers=_bearer(medewerker)
        )
    assert response.status_code == 403


def test_create_user_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/users", json={}, headers=_bearer(medewerker))
    assert response.status_code == 403


def test_update_user_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{uuid.uuid4()}",
            json={"is_active": False},
            headers=_bearer(medewerker),
        )
    assert response.status_code == 403


def test_update_user_nfc_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{uuid.uuid4()}/nfc",
            json={"nfc_tag_id": "NFC-001"},
            headers=_bearer(medewerker),
        )
    assert response.status_code == 403


# ─────────────────────────── 3. GET /me ──────────────────────────────────────
# /me is protected by get_current_user (any valid role), not get_current_admin.


def test_get_me_returns_current_user_for_any_role(client_with_overrides):
    # Works for a non-admin role to confirm it is NOT admin-gated.
    medewerker = _make_medewerker()
    # DB execute order: [1] get_current_user → medewerker
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/users/me", headers=_bearer(medewerker))
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == medewerker.email
    assert data["first_name"] == medewerker.first_name
    assert data["last_name"] == medewerker.last_name


# ─────────────────────────── 4. Admin: GET / ─────────────────────────────────


def test_list_users_returns_list_for_admin(client_with_overrides):
    admin = _make_admin()
    other = _make_medewerker()
    # DB execute order:
    # [1] get_current_user       → admin          (scalar_one_or_none)
    # [2] list_users body query  → [admin, other] (scalars().all())
    # [3] list_users total query → 2
    fake_db = _QueuedSession(admin, [admin, other], 2)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/users", headers=_bearer(admin))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_users_respects_skip_and_limit_params(client_with_overrides):
    admin = _make_admin()
    # DB execute order:
    # [1] get_current_user  → admin
    # [2] list_users query  → single user (simulating skip/limit result)
    # [3] list_users total  → 1
    fake_db = _QueuedSession(admin, [_make_medewerker()], 1)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/users?skip=0&limit=1", headers=_bearer(admin))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


# ─────────────────────────── 5. Admin: GET /{user_id} ────────────────────────


def test_get_user_by_id_returns_user_for_admin(client_with_overrides):
    admin = _make_admin()
    target = _make_medewerker()
    # DB execute order:
    # [1] get_current_user            → admin
    # [2] _get_user_with_role_or_404  → target
    fake_db = _QueuedSession(admin, target)
    with client_with_overrides(fake_db) as client:
        response = client.get(f"/api/v1/users/{target.user_id}", headers=_bearer(admin))
    assert response.status_code == 200
    assert response.json()["email"] == target.email


def test_get_user_by_id_returns_404_for_unknown_user(client_with_overrides):
    admin = _make_admin()
    # DB execute order:
    # [1] get_current_user            → admin
    # [2] _get_user_with_role_or_404  → None → 404
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.get(f"/api/v1/users/{uuid.uuid4()}", headers=_bearer(admin))
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


# ─────────────────────────── 6. Admin: POST / ────────────────────────────────


def test_create_user_returns_201_for_admin(client_with_overrides):
    admin = _make_admin()
    target_role_id = uuid.uuid4()
    created_user = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=target_role_id,
        first_name="Nieuw",
        last_name="Lid",
        email="nieuw@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    # DB execute order:
    # [1] get_current_user                       → admin
    # [2] email uniqueness check                 → None   (no collision)
    # [3] role_exists check                      → target_role_id  (exists)
    # [4] _get_user_with_role_or_404 after commit → created_user
    fake_db = _QueuedSession(admin, None, target_role_id, created_user)
    payload = {
        "first_name": "Nieuw",
        "last_name": "Lid",
        "email": "nieuw@easylend.be",
        "role_id": str(target_role_id),
        "pin": "securepin123",
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/users", json=payload, headers=_bearer(admin))
    assert response.status_code == 201
    assert response.json()["email"] == "nieuw@easylend.be"
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1  # User object was passed to db.add()


def test_create_user_returns_400_on_duplicate_email(client_with_overrides):
    admin = _make_admin()
    existing_user = _make_medewerker()
    # DB execute order:
    # [1] get_current_user       → admin
    # [2] email uniqueness check → existing_user (collision → 400)
    fake_db = _QueuedSession(admin, existing_user)
    payload = {
        "first_name": "Dubbel",
        "last_name": "Email",
        "email": existing_user.email,
        "role_id": str(uuid.uuid4()),
        "pin": "securepin123",
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/users", json=payload, headers=_bearer(admin))
    assert response.status_code == 400
    assert response.json()["detail"] == "Email address already exists."


def test_create_user_returns_400_on_invalid_role_id(client_with_overrides):
    admin = _make_admin()
    # DB execute order:
    # [1] get_current_user       → admin
    # [2] email uniqueness check → None    (no collision)
    # [3] role_exists check      → None    (role not found → 400)
    fake_db = _QueuedSession(admin, None, None)
    payload = {
        "first_name": "Nieuw",
        "last_name": "Lid",
        "email": "nieuw2@easylend.be",
        "role_id": str(uuid.uuid4()),
        "pin": "securepin123",
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/users", json=payload, headers=_bearer(admin))
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid role_id."


# ─────────────────────────── 7. Admin: PATCH /{user_id} ──────────────────────


def test_update_user_unblocks_locked_account(client_with_overrides):
    admin = _make_admin()
    locked_user = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Geblokkeerd",
        last_name="Account",
        email="blocked@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=5,
        locked_until=datetime(2026, 1, 1, tzinfo=UTC),
        is_active=True,
        ban_reason=None,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    # DB execute order:
    # [1] get_current_user                        → admin
    # [2] _get_user_with_role_or_404 (start)      → locked_user (setattr mutates in-place)
    # [3] _get_user_with_role_or_404 (after commit) → locked_user (now mutated)
    fake_db = _QueuedSession(admin, locked_user, locked_user)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{locked_user.user_id}",
            json={"failed_login_attempts": 0, "locked_until": None},
            headers=_bearer(admin),
        )
    assert response.status_code == 200
    # setattr applied to the SimpleNamespace in-place
    assert locked_user.failed_login_attempts == 0
    assert locked_user.locked_until is None
    assert fake_db.commit_calls == 1


def test_update_user_returns_404_for_unknown_user(client_with_overrides):
    admin = _make_admin()
    # DB execute order:
    # [1] get_current_user            → admin
    # [2] _get_user_with_role_or_404  → None → 404
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{uuid.uuid4()}",
            json={"is_active": False},
            headers=_bearer(admin),
        )
    assert response.status_code == 404


# ─────────────────────────── 8. Admin: PATCH /{user_id}/nfc ──────────────────


def test_update_user_nfc_links_new_tag(client_with_overrides):
    admin = _make_admin()
    target_user = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Geen",
        last_name="NFC",
        email="nonfc@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    updated_user = SimpleNamespace(
        **{**vars(target_user), "nfc_tag_id": "NFC-NIEUW-007"}
    )
    # DB execute order:
    # [1] get_current_user                          → admin
    # [2] _get_user_with_role_or_404                → target_user
    # [3] NFC uniqueness check                      → None (tag available)
    # [4] _get_user_with_role_or_404 (after commit) → updated_user
    fake_db = _QueuedSession(admin, target_user, None, updated_user)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{target_user.user_id}/nfc",
            json={"nfc_tag_id": "NFC-NIEUW-007"},
            headers=_bearer(admin),
        )
    assert response.status_code == 200
    assert response.json()["nfc_tag_id"] == "NFC-NIEUW-007"
    assert fake_db.commit_calls == 1


def test_update_user_nfc_returns_400_on_duplicate_tag(client_with_overrides):
    admin = _make_admin()
    target_user = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Target",
        last_name="User",
        email="target@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    tag_owner = _make_medewerker()
    # DB execute order:
    # [1] get_current_user            → admin
    # [2] _get_user_with_role_or_404  → target_user
    # [3] NFC uniqueness check        → tag_owner (collision → 400)
    fake_db = _QueuedSession(admin, target_user, tag_owner)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{target_user.user_id}/nfc",
            json={"nfc_tag_id": tag_owner.nfc_tag_id},
            headers=_bearer(admin),
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "NFC tag is already linked to another user."

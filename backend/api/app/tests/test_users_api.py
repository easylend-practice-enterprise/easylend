import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.tests.conftest import _bearer, _make_admin, _make_medewerker, _QueuedSession

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
        first_name="New",
        last_name="Member",
        email="new@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        is_anonymized=False,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    # DB execute order:
    # [1] get_current_user                       → admin
    # [2] email uniqueness check                 → None   (no collision)
    # [3] role_exists check                      → target_role_id  (exists)
    # [4] _get_user_with_role_or_404 after commit → created_user
    fake_db = _QueuedSession(admin, None, target_role_id, created_user)
    payload = {
        "first_name": "New",
        "last_name": "Member",
        "email": "new@easylend.be",
        "role_id": str(target_role_id),
        "pin": "securepin123",
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/users", json=payload, headers=_bearer(admin))
    assert response.status_code == 201
    assert response.json()["email"] == "new@easylend.be"
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
        "first_name": "New",
        "last_name": "Member",
        "email": "new2@easylend.be",
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
        first_name="Blocked",
        last_name="Account",
        email="blocked@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=5,
        locked_until=datetime(2026, 1, 1, tzinfo=UTC),
        is_active=True,
        ban_reason=None,
        is_anonymized=False,
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
        first_name="No",
        last_name="NFC",
        email="nonfc@easylend.be",
        nfc_tag_id=None,
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        is_anonymized=False,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    updated_user = SimpleNamespace(**{**vars(target_user), "nfc_tag_id": "NFC-NEW-007"})
    # DB execute order:
    # [1] get_current_user                          → admin
    # [2] _get_user_with_role_or_404                → target_user
    # [3] NFC uniqueness check                      → None (tag available)
    # [4] _get_user_with_role_or_404 (after commit) → updated_user
    fake_db = _QueuedSession(admin, target_user, None, updated_user)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/users/{target_user.user_id}/nfc",
            json={"nfc_tag_id": "NFC-NEW-007"},
            headers=_bearer(admin),
        )
    assert response.status_code == 200
    assert response.json()["nfc_tag_id"] == "NFC-NEW-007"
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
        is_anonymized=False,
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


# ──────────────── 9. Admin: POST /{user_id}/anonymize ────────────────────────


def test_anonymize_user_success(client_with_overrides):
    admin = _make_admin()
    target_user = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Real",
        last_name="Person",
        email="real@easylend.be",
        nfc_tag_id="NFC-REAL-001",
        pin_hash="real_hash",
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        is_anonymized=False,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    # Clone the user with anonymized=True for the re-fetch after commit
    anonymized_user = SimpleNamespace(
        **{
            k: v
            for k, v in vars(target_user).items()
            if k
            not in (
                "first_name",
                "last_name",
                "email",
                "nfc_tag_id",
                "pin_hash",
                "is_active",
                "is_anonymized",
                "role",
            )
        },
        first_name="Anonymized",
        last_name="User",
        email=f"anon_{uuid.uuid4()}@easylend.local",
        nfc_tag_id=None,
        pin_hash="ANONYMIZED",
        is_active=False,
        is_anonymized=True,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    # DB execute order:
    # [1] get_current_user                       → admin
    # [2] _get_user_with_role_or_404             → target_user (mutated in-place)
    # [3] log_audit_event execute (FOR UPDATE)   → None  (no prior audit log)
    # [4] _get_user_with_role_or_404 after commit → anonymized_user
    fake_db = _QueuedSession(admin, target_user, None, anonymized_user)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/users/{target_user.user_id}/anonymize",
            headers=_bearer(admin),
        )
    assert response.status_code == 200
    assert response.json()["is_anonymized"] is True
    assert response.json()["first_name"] == "Anonymized"
    assert response.json()["last_name"] == "User"
    assert response.json()["email"].startswith("anon_")
    assert response.json()["email"].endswith("@easylend.local")
    assert response.json()["nfc_tag_id"] is None
    assert response.json()["is_active"] is False
    assert fake_db.commit_calls == 1
    assert any(
        isinstance(o.__class__.__name__, str) and "AuditLog" in str(type(o))
        for o in fake_db.added
    )


def test_anonymize_user_returns_400_when_already_anonymized(client_with_overrides):
    admin = _make_admin()
    already_anon = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Anonymized",
        last_name="User",
        email="anon_abc123@easylend.local",
        nfc_tag_id=None,
        pin_hash="ANONYMIZED",
        failed_login_attempts=0,
        locked_until=None,
        is_active=False,
        ban_reason=None,
        is_anonymized=True,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    # DB execute order:
    # [1] get_current_user            → admin
    # [2] _get_user_with_role_or_404  → already_anon (is_anonymized=True → 400)
    fake_db = _QueuedSession(admin, already_anon)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/users/{already_anon.user_id}/anonymize",
            headers=_bearer(admin),
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "User is already anonymized."


def test_anonymize_user_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/users/{uuid.uuid4()}/anonymize",
            headers=_bearer(medewerker),
        )
    assert response.status_code == 403


def test_anonymize_user_returns_404_for_unknown_user(client_with_overrides):
    admin = _make_admin()
    # DB execute order:
    # [1] get_current_user            → admin
    # [2] _get_user_with_role_or_404  → None → 404
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            f"/api/v1/users/{uuid.uuid4()}/anonymize",
            headers=_bearer(admin),
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_anonymize_user_retries_on_integrity_error(client_with_overrides):
    """Verify that IntegrityError on the first db.commit() triggers a retry loop
    that eventually succeeds on the second attempt."""
    from unittest.mock import AsyncMock, patch

    from sqlalchemy.exc import IntegrityError

    admin = _make_admin()
    target_user = SimpleNamespace(
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        first_name="Real",
        last_name="Person",
        email="real@easylend.be",
        nfc_tag_id="NFC-REAL-001",
        pin_hash="real_hash",
        failed_login_attempts=0,
        locked_until=None,
        is_active=True,
        ban_reason=None,
        is_anonymized=False,
        role=SimpleNamespace(role_name="Medewerker"),
    )
    anon_user = SimpleNamespace(
        user_id=target_user.user_id,
        role_id=target_user.role_id,
        first_name="Anonymized",
        last_name="User",
        email=f"anon_{uuid.uuid4()}@easylend.local",
        nfc_tag_id=None,
        pin_hash="ANONYMIZED",
        failed_login_attempts=0,
        locked_until=None,
        is_active=False,
        ban_reason=None,
        is_anonymized=True,
        role=SimpleNamespace(role_name="Medewerker"),
    )

    # Track which commit attempt we're on so we can raise on #1 and succeed on #2.
    commit_attempt = [0]

    async def _fake_commit():
        commit_attempt[0] += 1
        if commit_attempt[0] == 1:
            raise IntegrityError("stmt", "params", Exception("orig"))
        # On second attempt, do nothing (commit simulated as successful).

    # Patch log_audit_event so it doesn't consume the db.execute queue.
    fake_audit_log = AsyncMock()

    # _QueuedSession returns anon_user on the final _get_user_with_role_or_404 call.
    fake_db = _QueuedSession(admin, target_user, anon_user)
    # Replace commit with our version that raises on attempt 1.
    fake_db.commit = _fake_commit

    with patch("app.api.v1.endpoints.users.log_audit_event", fake_audit_log):
        with client_with_overrides(fake_db) as client:
            response = client.post(
                f"/api/v1/users/{target_user.user_id}/anonymize",
                headers=_bearer(admin),
            )

    assert response.status_code == 200
    assert response.json()["is_anonymized"] is True
    # log_audit_event should have been called exactly twice (once per loop iteration).
    assert fake_audit_log.call_count == 2
    # commit should have been called twice (first raises, second succeeds).
    assert commit_attempt[0] == 2

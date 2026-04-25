"""
Tests for the Equipment CRUD endpoints: ELP-26.

Coverage:
    1. RBAC / Auth      : unauthenticated → 401, medewerker → 403
    2. Categories       : GET list (any auth), POST (admin), PUT (admin + 404)
    3. Kiosks           : POST (admin, 201), PUT status (admin + 404)
    4. Lockers          : POST (admin, 201), POST with invalid kiosk_id (400)
    5. Assets           : POST (admin, 201), GET list filter, GET by id, PUT,
                           DELETE soft-delete (204), DELETE invalid id (404)

_QueuedSession execute() ordering: every `await db.execute(query)` pops one
slot from the queue in FIFO order. Each test documents the exact slots used.
`await db.refresh(obj)` mutates the object in-place to assign missing UUIDs.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tests.conftest import (
    _bearer,
    _make_admin,
    _make_medewerker,
    _QueuedSession,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_category(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        category_id=uuid.uuid4(),
        category_name=kwargs.get("category_name", "Laptops"),
    )


def _make_kiosk(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        name=kwargs.get("name", "Kiosk A"),
        location_description=kwargs.get("location_description", "Building 1, Floor 2"),
        kiosk_status=kwargs.get("kiosk_status", "ONLINE"),
    )


def _make_locker(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        kiosk_id=kwargs.get("kiosk_id", uuid.uuid4()),
        logical_number=kwargs.get("logical_number", 1),
        locker_status=kwargs.get("locker_status", "AVAILABLE"),
    )


def _make_asset(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=kwargs.get("asset_id", uuid.uuid4()),
        category_id=kwargs.get("category_id", uuid.uuid4()),
        locker_id=kwargs.get("locker_id", uuid.uuid4()),
        name=kwargs.get("name", "HP EliteBook 840"),
        aztec_code=kwargs.get("aztec_code", "AZT-001"),
        asset_status=kwargs.get("asset_status", "AVAILABLE"),
        is_deleted=kwargs.get("is_deleted", False),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. RBAC / Auth
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/v1/kiosks", {"name": "K1", "location_description": "Floor 1"}),
        (
            "post",
            "/api/v1/assets",
            {
                "name": "HP Laptop",
                "aztec_code": "AZT-X",
                "category_id": str(uuid.uuid4()),
            },
        ),
    ],
)
def test_write_endpoint_returns_401_without_token(
    method, path, body, client_with_overrides
):
    """POST to admin-only write endpoints without a Bearer token → 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = getattr(client, method)(path, json=body)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/v1/kiosks", {"name": "K1", "location_description": "Floor 1"}),
        (
            "post",
            "/api/v1/assets",
            {
                "name": "HP Laptop",
                "aztec_code": "AZT-X",
                "category_id": str(uuid.uuid4()),
            },
        ),
    ],
)
def test_write_endpoint_returns_403_for_medewerker(
    method, path, body, client_with_overrides
):
    """POST to admin-only write endpoints with a Medewerker JWT → 403.

    DB execute order:
    [1] get_current_user → medewerker   (get_current_admin checks role → 403)
    """
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = getattr(client, method)(path, json=body, headers=_bearer(medewerker))
    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 2. Categories
# ─────────────────────────────────────────────────────────────────────────────


def test_list_categories_is_accessible_by_medewerker(client_with_overrides):
    """GET /categories should be readable by any authenticated user (no admin gate).

    DB execute order:
    [1] get_current_user  → medewerker
    [2] list query        → [laptop_cat, tablet_cat]
    [3] count query       → 2
    """
    medewerker = _make_medewerker()
    laptop_cat = _make_category(category_name="Laptops")
    tablet_cat = _make_category(category_name="Tablets")

    fake_db = _QueuedSession(medewerker, [laptop_cat, tablet_cat], 2)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/categories", headers=_bearer(medewerker))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["category_name"] == "Laptops"


def test_list_categories_returns_401_without_token(client_with_overrides):
    """GET /categories without a JWT → 401 (any-auth gate still enforced)."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/categories")
    assert response.status_code == 401


def test_create_category_returns_201_for_admin(client_with_overrides):
    """POST /categories (admin) creates a new category and returns 201.

    DB execute order:
    [1] get_current_user → admin
    """
    admin = _make_admin()

    # Queue: admin for auth, then refresh() is a no-op, response reflects new_cat
    # Because create_category does db.add() + commit() + refresh(): no extra executes.
    fake_db = _QueuedSession(admin)
    # Patch db.add so we can inspect the object that was added.
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/categories",
            json={"category_name": "Calculators"},
            headers=_bearer(admin),
        )

    assert response.status_code == 201
    # The response is built from the SQLAlchemy object passed to db.add().
    # Since refresh() is a no-op, category_name comes from the object we constructed.
    assert response.json()["category_name"] == "Calculators"
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1


def test_create_category_returns_403_for_medewerker(client_with_overrides):
    """POST /categories as medewerker → 403.

    DB execute order:
    [1] get_current_user → medewerker
    """
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.post(
            "/api/v1/categories",
            json={"category_name": "Forbidden"},
            headers=_bearer(medewerker),
        )
    assert response.status_code == 403


def test_update_category_returns_404_for_unknown_category(client_with_overrides):
    """PATCH /categories/{id} where the category doesn't exist → 404.

    DB execute order:
    [1] get_current_user           → admin
    [2] _get_category_or_404       → None → 404
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/categories/{uuid.uuid4()}",
            json={"category_name": "Updated"},
            headers=_bearer(admin),
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found."


def test_update_category_returns_200_and_mutates_name(client_with_overrides):
    """PATCH /categories/{id} (admin) renames the category in-place.

    DB execute order:
    [1] get_current_user     → admin
    [2] _get_category_or_404 → existing_cat
    """
    admin = _make_admin()
    existing_cat = _make_category(category_name="Old Name")

    fake_db = _QueuedSession(admin, existing_cat)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/categories/{existing_cat.category_id}",
            json={"category_name": "New Name"},
            headers=_bearer(admin),
        )

    assert response.status_code == 200
    assert response.json()["category_name"] == "New Name"
    assert existing_cat.category_name == "New Name"  # mutated in-place by setattr
    assert fake_db.commit_calls == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Kiosks
# ─────────────────────────────────────────────────────────────────────────────


def test_create_kiosk_returns_201_for_admin(client_with_overrides):
    """POST /kiosks (admin) registers a new kiosk and returns 201.

    DB execute order:
    [1] get_current_user → admin
    (create_kiosk has no extra execute calls before commit + refresh)
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin)

    payload = {
        "name": "Kiosk Alpha",
        "location_description": "Main Hall, Ground Floor",
        "kiosk_status": "ONLINE",
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/kiosks", json=payload, headers=_bearer(admin))

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Kiosk Alpha"
    assert data["location_description"] == "Main Hall, Ground Floor"
    assert data["kiosk_status"] == "ONLINE"
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1


def test_list_kiosks_returns_401_without_token(client_with_overrides):
    """GET /kiosks without any token → 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/kiosks")
    assert response.status_code == 401


def test_update_kiosk_status_returns_404_for_unknown_kiosk(client_with_overrides):
    """PATCH /kiosks/{id}/status where kiosk doesn't exist → 404.

    DB execute order:
    [1] get_current_user  → admin
    [2] _get_kiosk_or_404 → None → 404
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/kiosks/{uuid.uuid4()}/status",
            json={"kiosk_status": "MAINTENANCE"},
            headers=_bearer(admin),
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Kiosk not found."


def test_update_kiosk_status_returns_200_and_mutates_status(
    client_with_overrides, monkeypatch
):
    """PATCH /kiosks/{id}/status (admin) transitions kiosk to MAINTENANCE.

    DB execute order:
    [1] get_current_user  → admin
    [2] _get_kiosk_or_404 → kiosk
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", AsyncMock())

    admin = _make_admin()
    kiosk = _make_kiosk(kiosk_status="ONLINE")

    fake_db = _QueuedSession(admin, kiosk)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/kiosks/{kiosk.kiosk_id}/status",
            json={"kiosk_status": "MAINTENANCE"},
            headers=_bearer(admin),
        )

    assert response.status_code == 200
    assert response.json()["kiosk_status"] == "MAINTENANCE"
    assert kiosk.kiosk_status == "MAINTENANCE"  # mutated in-place
    assert fake_db.commit_calls == 1


def test_update_kiosk_status_skips_audit_when_status_is_unchanged(
    client_with_overrides, monkeypatch
):
    audit_mock = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", audit_mock)

    admin = _make_admin()
    kiosk = _make_kiosk(kiosk_status="ONLINE")

    fake_db = _QueuedSession(admin, kiosk)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/kiosks/{kiosk.kiosk_id}/status",
            json={"kiosk_status": "ONLINE"},
            headers=_bearer(admin),
        )

    assert response.status_code == 200
    assert audit_mock.await_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Lockers
# ─────────────────────────────────────────────────────────────────────────────


def test_create_locker_returns_201_for_admin(client_with_overrides):
    """POST /lockers (admin) creates a locker attached to an existing kiosk.

    DB execute order:
    [1] get_current_user   → admin
    [2] kiosk_exists check → kiosk_id (scalar: exists)
    """
    admin = _make_admin()
    kiosk_id = uuid.uuid4()

    # [1] auth, [2] kiosk FK check returns kiosk_id (truthy scalar)
    fake_db = _QueuedSession(admin, kiosk_id)

    payload = {
        "kiosk_id": str(kiosk_id),
        "logical_number": 3,
        "locker_status": "AVAILABLE",
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/lockers", json=payload, headers=_bearer(admin))

    assert response.status_code == 201
    data = response.json()
    assert data["logical_number"] == 3
    assert data["locker_status"] == "AVAILABLE"
    assert data["kiosk_id"] == str(kiosk_id)
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1


def test_create_locker_returns_400_for_invalid_kiosk_id(client_with_overrides):
    """POST /lockers with a kiosk_id that doesn't exist → 400.

    DB execute order:
    [1] get_current_user   → admin
    [2] kiosk_exists check → None (kiosk not found → 400)
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)

    payload = {
        "kiosk_id": str(uuid.uuid4()),
        "logical_number": 1,
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/lockers", json=payload, headers=_bearer(admin))

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid kiosk_id: kiosk does not exist."
    assert fake_db.commit_calls == 0  # no commit on validation failure


def test_get_locker_by_id_returns_404_for_unknown_locker(client_with_overrides):
    """GET /lockers/{id} for a non-existent locker → 404.

    DB execute order:
    [1] get_current_user   → admin
    [2] _get_locker_or_404 → None → 404
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.get(f"/api/v1/lockers/{uuid.uuid4()}", headers=_bearer(admin))
    assert response.status_code == 404
    assert response.json()["detail"] == "Locker not found."


def test_get_locker_by_id_returns_200_for_admin(client_with_overrides):
    """GET /lockers/{id} for an existing locker → 200.

    DB execute order:
    [1] get_current_user   → admin
    [2] _get_locker_or_404 → locker
    """
    admin = _make_admin()
    locker = _make_locker(logical_number=7)

    fake_db = _QueuedSession(admin, locker)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/lockers/{locker.locker_id}", headers=_bearer(admin)
        )
    assert response.status_code == 200
    assert response.json()["logical_number"] == 7


# ─────────────────────────────────────────────────────────────────────────────
# 5. Assets
# ─────────────────────────────────────────────────────────────────────────────


def test_create_asset_returns_201_for_admin(client_with_overrides, monkeypatch):
    """POST /assets (admin) registers a new asset with category + locker.

    DB execute order:
    [1] get_current_user      → admin
    [2] category_exists check → category_id (exists)
    [3] locker_exists check   → locker_id   (exists)
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", AsyncMock())

    admin = _make_admin()
    category_id = uuid.uuid4()
    locker_id = uuid.uuid4()

    fake_db = _QueuedSession(admin, category_id, locker_id)

    payload = {
        "name": "HP EliteBook 840 G9",
        "aztec_code": "AZT-LAP-001",
        "asset_status": "AVAILABLE",
        "category_id": str(category_id),
        "locker_id": str(locker_id),
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/assets", json=payload, headers=_bearer(admin))

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "HP EliteBook 840 G9"
    assert data["aztec_code"] == "AZT-LAP-001"
    assert data["asset_status"] == "AVAILABLE"
    assert data["is_deleted"] is False
    assert fake_db.commit_calls == 1
    assert len(fake_db.added) == 1


def test_create_asset_returns_400_for_invalid_category_id(client_with_overrides):
    """POST /assets with a category_id that doesn't exist → 400.

    DB execute order:
    [1] get_current_user      → admin
    [2] category_exists check → None (not found → 400)
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)

    payload = {
        "name": "Unknown Cat Asset",
        "aztec_code": "AZT-NO-CAT",
        "category_id": str(uuid.uuid4()),
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/assets", json=payload, headers=_bearer(admin))

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid category_id: category does not exist."


def test_create_asset_returns_400_for_invalid_locker_id(client_with_overrides):
    """POST /assets with a locker_id that doesn't exist → 400.

    DB execute order:
    [1] get_current_user      → admin
    [2] category_exists check → category_id (found)
    [3] locker_exists check   → None (not found → 400)
    """
    admin = _make_admin()
    category_id = uuid.uuid4()
    fake_db = _QueuedSession(admin, category_id, None)

    payload = {
        "name": "Misplaced Asset",
        "aztec_code": "AZT-BAD-LOCKER",
        "category_id": str(category_id),
        "locker_id": str(uuid.uuid4()),
    }
    with client_with_overrides(fake_db) as client:
        response = client.post("/api/v1/assets", json=payload, headers=_bearer(admin))

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid locker_id: locker does not exist."


def test_list_assets_is_accessible_by_medewerker(client_with_overrides):
    """GET /assets is accessible by any authenticated user (no admin gate).

    DB execute order:
    [1] get_current_user → medewerker
    [2] list query       → [asset_a, asset_b]
    [3] count query      → 2
    """
    medewerker = _make_medewerker()
    asset_a = _make_asset(name="Laptop A", aztec_code="AZT-A")
    asset_b = _make_asset(name="Laptop B", aztec_code="AZT-B")

    fake_db = _QueuedSession(medewerker, [asset_a, asset_b], 2)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/assets", headers=_bearer(medewerker))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_assets_with_status_filter(client_with_overrides):
    """GET /assets?asset_status=AVAILABLE filters by status.

    DB execute order:
    [1] get_current_user → admin
    [2] filtered list    → [available_asset]
    [3] filtered count   → 1
    """
    admin = _make_admin()
    available_asset = _make_asset(asset_status="AVAILABLE")

    fake_db = _QueuedSession(admin, [available_asset], 1)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            "/api/v1/assets?asset_status=AVAILABLE", headers=_bearer(admin)
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["asset_status"] == "AVAILABLE"


def test_get_asset_by_id_returns_200_for_any_authenticated_user(client_with_overrides):
    """GET /assets/{id} is accessible by medewerker (not admin-gated).

    DB execute order:
    [1] get_current_user    → medewerker
    [2] _get_asset_or_404   → asset
    """
    medewerker = _make_medewerker()
    asset = _make_asset(name="ThinkPad X1", aztec_code="AZT-X1")

    fake_db = _QueuedSession(medewerker, asset)
    with client_with_overrides(fake_db) as client:
        response = client.get(
            f"/api/v1/assets/{asset.asset_id}", headers=_bearer(medewerker)
        )

    assert response.status_code == 200
    assert response.json()["name"] == "ThinkPad X1"
    assert response.json()["aztec_code"] == "AZT-X1"


def test_get_asset_by_id_returns_404_for_unknown_asset(client_with_overrides):
    """GET /assets/{id} for a non-existent asset → 404.

    DB execute order:
    [1] get_current_user  → admin
    [2] _get_asset_or_404 → None → 404
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.get(f"/api/v1/assets/{uuid.uuid4()}", headers=_bearer(admin))
    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found."


def test_update_asset_returns_200_and_mutates_status(
    client_with_overrides, monkeypatch
):
    """PATCH /assets/{id} (admin) changes asset_status to MAINTENANCE in-place.

    DB execute order:
    [1] get_current_user  → admin
    [2] _get_asset_or_404 → asset
    """
    from unittest.mock import AsyncMock

    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", AsyncMock())

    admin = _make_admin()
    asset = _make_asset(asset_status="AVAILABLE")

    fake_db = _QueuedSession(admin, asset)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/assets/{asset.asset_id}",
            json={"asset_status": "MAINTENANCE"},
            headers=_bearer(admin),
        )

    assert response.status_code == 200
    assert response.json()["asset_status"] == "MAINTENANCE"
    assert asset.asset_status == "MAINTENANCE"  # setattr mutated in-place
    assert fake_db.commit_calls == 1


def test_update_asset_skips_audit_when_status_is_unchanged(
    client_with_overrides, monkeypatch
):
    audit_mock = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", audit_mock)

    admin = _make_admin()
    asset = _make_asset(asset_status="AVAILABLE")

    fake_db = _QueuedSession(admin, asset)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/assets/{asset.asset_id}",
            json={"asset_status": "AVAILABLE"},
            headers=_bearer(admin),
        )

    assert response.status_code == 200
    assert audit_mock.await_count == 0


def test_soft_delete_asset_returns_204_for_admin(client_with_overrides):
    """DELETE /assets/{id} (admin) soft-deletes the asset and returns 204 No Content.

    `is_deleted` is toggled to True on the object; no response body is returned.

    DB execute order:
    [1] get_current_user  → admin
    [2] _get_asset_or_404 → asset
    """
    admin = _make_admin()
    asset = _make_asset()
    assert asset.is_deleted is False  # precondition

    fake_db = _QueuedSession(admin, asset)
    with client_with_overrides(fake_db) as client:
        response = client.delete(
            f"/api/v1/assets/{asset.asset_id}", headers=_bearer(admin)
        )

    assert response.status_code == 204
    assert response.content == b""  # 204 No Content: empty body
    assert asset.is_deleted is True  # setattr mutated in-place by soft_delete_asset
    assert fake_db.commit_calls == 1


def test_soft_delete_asset_returns_404_for_unknown_asset(client_with_overrides):
    """DELETE /assets/{id} for a non-existent asset → 404.

    DB execute order:
    [1] get_current_user  → admin
    [2] _get_asset_or_404 → None → 404
    """
    admin = _make_admin()
    fake_db = _QueuedSession(admin, None)
    with client_with_overrides(fake_db) as client:
        response = client.delete(
            f"/api/v1/assets/{uuid.uuid4()}", headers=_bearer(admin)
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found."


def test_soft_delete_asset_returns_403_for_medewerker(client_with_overrides):
    """DELETE /assets/{id} by a medewerker → 403.

    DB execute order:
    [1] get_current_user → medewerker (role check → 403)
    """
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.delete(
            f"/api/v1/assets/{uuid.uuid4()}", headers=_bearer(medewerker)
        )
    assert response.status_code == 403


def test_list_lockers_returns_list_for_admin(client_with_overrides):
    """GET /lockers returns 200 for admin and includes items."""
    admin = _make_admin()
    locker = SimpleNamespace(
        locker_id=uuid.uuid4(),
        kiosk_id=uuid.uuid4(),
        logical_number=1,
        locker_status="AVAILABLE",
    )
    fake_db = _QueuedSession(admin, [locker], 1)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/lockers", headers=_bearer(admin))
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_list_lockers_returns_403_for_medewerker(client_with_overrides):
    """GET /lockers returns 403 for medewerker (admin-only endpoint)."""
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/lockers", headers=_bearer(medewerker))
    assert response.status_code == 403


def test_update_locker_status_returns_200_and_mutates(
    client_with_overrides, monkeypatch
):
    """PATCH /lockers/{id}/status correctly updates the status."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", AsyncMock())

    admin = _make_admin()
    locker = SimpleNamespace(
        locker_id=uuid.uuid4(),
        kiosk_id=uuid.uuid4(),
        logical_number=1,
        locker_status="AVAILABLE",
    )
    fake_db = _QueuedSession(admin, locker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/lockers/{locker.locker_id}/status",
            json={"locker_status": "MAINTENANCE"},
            headers=_bearer(admin),
        )
    assert response.status_code == 200
    assert response.json()["locker_status"] == "MAINTENANCE"


def test_update_locker_status_skips_audit_when_status_is_unchanged(
    client_with_overrides, monkeypatch
):
    audit_mock = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.equipment.log_audit_event", audit_mock)

    admin = _make_admin()
    locker = SimpleNamespace(
        locker_id=uuid.uuid4(),
        kiosk_id=uuid.uuid4(),
        logical_number=1,
        locker_status="AVAILABLE",
    )
    fake_db = _QueuedSession(admin, locker)
    with client_with_overrides(fake_db) as client:
        response = client.patch(
            f"/api/v1/lockers/{locker.locker_id}/status",
            json={"locker_status": "AVAILABLE"},
            headers=_bearer(admin),
        )

    assert response.status_code == 200
    assert audit_mock.await_count == 0


def test_get_catalog_as_non_admin_sees_grouped_counts(client_with_overrides):
    """GET /catalog as a non-admin returns grouped counts per category.

    Categories where all assets are borrowed or in-maintenance must still appear
    with available_count=0 (LEFT OUTER JOIN, not INNER JOIN). Verifies DRIFT-01.

    DB execute order:
    [1] get_current_user → medewerker
    [2] grouped query    → [(cat1_id, 'Laptops', 2), (cat2_id, 'Tablets', 0)]
    """
    medewerker = _make_medewerker()
    cat1_id = uuid.uuid4()
    cat2_id = uuid.uuid4()

    # The fake DB queue: [get_current_user → medewerker, grouped query → list of tuples]
    # cat2 (Tablets) has 0 available assets — the outerjoin must still emit this row.
    grouped_rows = [(cat1_id, "Laptops", 2), (cat2_id, "Tablets", 0)]
    fake_db = _QueuedSession(medewerker, grouped_rows)

    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/catalog", headers=_bearer(medewerker))

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # Laptops: 2 available
    laptops = next((r for r in data if r.get("category_id") == str(cat1_id)), None)
    assert laptops is not None
    assert laptops["category_name"] == "Laptops"
    assert laptops["available_count"] == 2

    # Tablets: 0 available — must still be present (DRIFT-01 regression guard)
    tablets = next((r for r in data if r.get("category_id") == str(cat2_id)), None)
    assert tablets is not None
    assert tablets["category_name"] == "Tablets"
    assert tablets["available_count"] == 0


def test_get_catalog_as_admin_sees_asset_details(client_with_overrides):
    """GET /catalog as admin returns per-asset rows including loan context."""
    admin = _make_admin()
    asset = _make_asset(name="Dell XPS", asset_status="BORROWED")

    # Queue: [get_current_user -> admin, admin query -> list of tuples (asset, loan_status, borrower_first_name, borrower_last_name)]
    admin_rows = [(asset, "ACTIVE", "Borrower", "Example")]
    fake_db = _QueuedSession(admin, admin_rows)

    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/catalog", headers=_bearer(admin))

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    first = data[0]
    assert first["asset_id"] == str(asset.asset_id)
    assert first["asset_name"] == "Dell XPS"
    assert first["loan_status"] == "ACTIVE"
    assert first["borrower_first_name"] == "Borrower"
    assert first["borrower_last_name"] == "Example"


def test_get_catalog_returns_401_without_token(client_with_overrides):
    """GET /catalog without Authorization header returns 401."""
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/catalog")

    assert response.status_code == 401

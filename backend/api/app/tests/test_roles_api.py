import uuid

from app.db.models import Role
from app.tests.conftest import (
    _bearer,
    _make_admin,
    _make_medewerker,
    _QueuedSession,
)


def test_list_roles_unauthenticated(client_with_overrides):
    with client_with_overrides(_QueuedSession()) as client:
        response = client.get("/api/v1/roles")
    assert response.status_code == 401


def test_list_roles_forbidden_for_non_admin(client_with_overrides):
    medewerker = _make_medewerker()
    fake_db = _QueuedSession(medewerker)
    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/roles", headers=_bearer(medewerker))
    assert response.status_code == 403


def test_list_roles_returns_list_for_admin(client_with_overrides):
    admin = _make_admin()
    admin.role.role_name = "ADMIN"
    role_admin = Role(role_id=uuid.uuid4(), role_name="ADMIN")

    # DB execute order:
    # [1] get_current_user -> admin
    # [2] list_roles query -> [role_admin]
    fake_db = _QueuedSession(admin, [role_admin])

    with client_with_overrides(fake_db) as client:
        response = client.get("/api/v1/roles", headers=_bearer(admin))

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["role_id"] == str(role_admin.role_id)
    assert data[0]["role_name"] == role_admin.role_name

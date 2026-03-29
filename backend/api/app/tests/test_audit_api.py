import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import app.core.audit as audit_core
from app.tests.conftest import (
    _bearer,
    _make_admin,
    _make_medewerker,
    _QueuedSession,
)


def _make_audit_entry(
    audit_id: uuid.UUID,
    user_id,
    action_type: str,
    payload: dict,
    previous_hash: str,
    current_hash: str,
    created_at: datetime,
):
    return SimpleNamespace(
        audit_id=audit_id,
        user_id=user_id,
        action_type=action_type,
        payload=payload,
        previous_hash=previous_hash,
        current_hash=current_hash,
        created_at=created_at,
    )


def test_audit_endpoints_return_403_for_non_admin(client_with_overrides):
    """Non-admin users should get 403 on audit endpoints."""
    medewerker = _make_medewerker()

    # GET / -> 403
    with client_with_overrides(_QueuedSession(medewerker)) as client:
        resp = client.get("/api/v1/audit/", headers=_bearer(medewerker))
    assert resp.status_code == 403

    # GET /verify -> 403
    with client_with_overrides(_QueuedSession(medewerker)) as client:
        resp = client.get("/api/v1/audit/verify", headers=_bearer(medewerker))
    assert resp.status_code == 403


def test_audit_list_returns_200_with_logs(client_with_overrides):
    admin = _make_admin()
    now = datetime.now(UTC)

    log1 = _make_audit_entry(
        uuid.uuid4(),
        admin.user_id,
        "TEST_ACTION_1",
        {"k": "v1"},
        audit_core._GENESIS_AUDIT_HASH,
        audit_core._compute_audit_hash(
            audit_core._GENESIS_AUDIT_HASH, "TEST_ACTION_1", {"k": "v1"}
        ),
        now,
    )

    log2 = _make_audit_entry(
        uuid.uuid4(),
        admin.user_id,
        "TEST_ACTION_2",
        {"k": "v2"},
        log1.current_hash,
        audit_core._compute_audit_hash(log1.current_hash, "TEST_ACTION_2", {"k": "v2"}),
        now,
    )

    fake_db = _QueuedSession(admin, [log1, log2])
    with client_with_overrides(fake_db) as client:
        resp = client.get("/api/v1/audit/", headers=_bearer(admin))

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 2
    # basic content checks
    assert data[0]["action_type"] in ("TEST_ACTION_1", "TEST_ACTION_2")


def test_audit_verify_valid_chain(client_with_overrides):
    admin = _make_admin()

    # Build a 2-entry valid chain
    running = audit_core._GENESIS_AUDIT_HASH
    a1_id = uuid.uuid4()
    a1_payload = {"x": 1}
    a1_current = audit_core._compute_audit_hash(running, "A1", a1_payload)
    a1 = _make_audit_entry(
        a1_id,
        admin.user_id,
        "A1",
        a1_payload,
        running,
        a1_current,
        datetime.now(UTC),
    )

    running = a1_current
    a2_id = uuid.uuid4()
    a2_payload = {"y": 2}
    a2_current = audit_core._compute_audit_hash(running, "A2", a2_payload)
    a2 = _make_audit_entry(
        a2_id,
        admin.user_id,
        "A2",
        a2_payload,
        running,
        a2_current,
        datetime.now(UTC),
    )

    fake_db = _QueuedSession(admin, [a1, a2])
    with client_with_overrides(fake_db) as client:
        resp = client.get("/api/v1/audit/verify", headers=_bearer(admin))

    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert resp.json()["tampered_record_id"] is None


def test_audit_verify_detects_tampered_record(client_with_overrides):
    admin = _make_admin()

    # Build a chain where the 2nd record's current_hash is wrong
    running = audit_core._GENESIS_AUDIT_HASH
    a1_id = uuid.uuid4()
    a1_payload = {"x": 1}
    a1_current = audit_core._compute_audit_hash(running, "A1", a1_payload)
    a1 = _make_audit_entry(
        a1_id,
        admin.user_id,
        "A1",
        a1_payload,
        running,
        a1_current,
        datetime.now(UTC),
    )

    # a2 has a malformed current_hash
    a2_id = uuid.uuid4()
    a2_payload = {"y": 2}
    a2 = _make_audit_entry(
        a2_id,
        admin.user_id,
        "A2",
        a2_payload,
        a1_current,
        "bad_hash",
        datetime.now(UTC),
    )

    fake_db = _QueuedSession(admin, [a1, a2])
    with client_with_overrides(fake_db) as client:
        resp = client.get("/api/v1/audit/verify", headers=_bearer(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is False
    assert body["tampered_record_id"] == str(a2_id)


def test_audit_verify_empty_chain(client_with_overrides):
    """An empty audit table is considered a valid (empty) chain by design."""
    admin = _make_admin()

    fake_db = _QueuedSession(admin, [])
    with client_with_overrides(fake_db) as client:
        resp = client.get("/api/v1/audit/verify", headers=_bearer(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is True
    assert body["tampered_record_id"] is None


def test_audit_verify_single_entry(client_with_overrides):
    """A single-record chain with the correct genesis previous_hash is valid."""
    admin = _make_admin()

    genesis = audit_core._GENESIS_AUDIT_HASH
    payload = {"event": "init"}
    current = audit_core._compute_audit_hash(genesis, "CHAIN_INIT", payload)
    log = _make_audit_entry(
        uuid.uuid4(),
        admin.user_id,
        "CHAIN_INIT",
        payload,
        genesis,
        current,
        datetime.now(UTC),
    )

    fake_db = _QueuedSession(admin, [log])
    with client_with_overrides(fake_db) as client:
        resp = client.get("/api/v1/audit/verify", headers=_bearer(admin))

    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert resp.json()["tampered_record_id"] is None


def test_audit_verify_continuity_violation(client_with_overrides):
    """Detect a record whose current_hash is internally correct but previous_hash breaks the chain."""
    admin = _make_admin()

    # a1 is clean
    genesis = audit_core._GENESIS_AUDIT_HASH
    a1_payload = {"x": 1}
    a1_current = audit_core._compute_audit_hash(genesis, "A1", a1_payload)
    a1 = _make_audit_entry(
        uuid.uuid4(),
        admin.user_id,
        "A1",
        a1_payload,
        genesis,
        a1_current,
        datetime.now(UTC),
    )

    # a2's current_hash is correct for its own data BUT its previous_hash is
    # wrong (points to genesis instead of a1's hash), simulating a re-linked record
    wrong_previous = genesis  # should be a1_current
    a2_payload = {"y": 2}
    a2_id = uuid.uuid4()
    a2 = _make_audit_entry(
        a2_id,
        admin.user_id,
        "A2",
        a2_payload,
        wrong_previous,
        audit_core._compute_audit_hash(wrong_previous, "A2", a2_payload),
        datetime.now(UTC),
    )

    fake_db = _QueuedSession(admin, [a1, a2])
    with client_with_overrides(fake_db) as client:
        resp = client.get("/api/v1/audit/verify", headers=_bearer(admin))

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_valid"] is False
    assert body["tampered_record_id"] == str(a2_id)

import uuid
from types import SimpleNamespace

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.db.database import get_db
from app.main import app
from app.tests.conftest import _QueuedSession

client = TestClient(app)


def test_websocket_missing_token() -> None:
    try:
        with client.websocket_connect("/ws/visionbox/kiosk_1"):
            pass
        pytest.fail("Expected websocket rejection for missing token")
    except WebSocketDenialResponse as exc:
        assert exc.status_code == status.HTTP_403_FORBIDDEN
    except WebSocketDisconnect as exc:
        assert exc.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_invalid_token() -> None:
    try:
        with client.websocket_connect(
            "/ws/visionbox/kiosk_1", headers={"X-Device-Token": "invalid_token"}
        ):
            pass
        pytest.fail("Expected websocket rejection for invalid token")
    except WebSocketDenialResponse as exc:
        assert exc.status_code == status.HTTP_403_FORBIDDEN
    except WebSocketDisconnect as exc:
        assert exc.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_valid_vision_box_token() -> None:
    with client.websocket_connect(
        "/ws/visionbox/kiosk_1", headers={"X-Device-Token": settings.VISION_BOX_API_KEY}
    ) as websocket:
        websocket.send_json({"action": "ping"})


def test_websocket_valid_simulation_token() -> None:
    with client.websocket_connect(
        "/ws/visionbox/kiosk_2", headers={"X-Device-Token": settings.SIMULATION_API_KEY}
    ) as websocket:
        websocket.send_json({"action": "ping"})


def test_websocket_slot_closed_event_is_accepted() -> None:
    with client.websocket_connect(
        "/ws/visionbox/kiosk_3", headers={"X-Device-Token": settings.VISION_BOX_API_KEY}
    ) as websocket:
        websocket.send_text('{"event":"slot_closed","locker_id":"12"}')


def test_websocket_slot_closed_event_updates_locker() -> None:
    locker_id = uuid.uuid4()
    loan_id = uuid.uuid4()
    locker = SimpleNamespace(locker_id=locker_id, locker_status="AVAILABLE")
    loan = SimpleNamespace(loan_id=loan_id)
    fake_db = _QueuedSession(locker, loan)

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with client.websocket_connect(
            "/ws/visionbox/kiosk_4",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
        ) as websocket:
            websocket.send_json(
                {
                    "event": "slot_closed",
                    "locker_id": str(locker_id),
                    "loan_id": str(loan_id),
                }
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert fake_db.commit_calls == 1
    assert locker.locker_status == "OCCUPIED"

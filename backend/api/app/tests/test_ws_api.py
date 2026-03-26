import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
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
    locker_id = str(uuid.uuid4())
    with client.websocket_connect(
        "/ws/visionbox/kiosk_3", headers={"X-Device-Token": settings.VISION_BOX_API_KEY}
    ) as websocket:
        websocket.send_text(f'{{"event":"slot_closed","locker_id":"{locker_id}"}}')


def test_websocket_slot_closed_event_updates_locker() -> None:
    locker_id = uuid.uuid4()
    locker = SimpleNamespace(locker_id=locker_id, locker_status="AVAILABLE")
    fake_db = _QueuedSession(locker)

    class _FakeSessionCtx:
        async def __aenter__(self):
            return fake_db

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

    with patch("app.api.ws.AsyncSessionLocal", return_value=_FakeSessionCtx()):
        with client.websocket_connect(
            "/ws/visionbox/kiosk_4",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
        ) as websocket:
            websocket.send_json(
                {
                    "event": "slot_closed",
                    "locker_id": str(locker_id),
                }
            )

    assert fake_db.commit_calls == 1
    assert locker.locker_status == "OCCUPIED"

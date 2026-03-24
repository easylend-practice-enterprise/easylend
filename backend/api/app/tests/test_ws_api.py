import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_websocket_missing_token() -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/visionbox/kiosk_1"):
            pass
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_invalid_token() -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/ws/visionbox/kiosk_1", headers={"X-Device-Token": "invalid_token"}
        ):
            pass
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


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

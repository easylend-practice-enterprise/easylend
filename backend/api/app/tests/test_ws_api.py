import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.main import app

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
    with patch(
        "app.api.ws._verify_kiosk_exists",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with client.websocket_connect(
            "/ws/visionbox/kiosk_1",
            headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
        ) as websocket:
            websocket.send_json({"action": "ping"})


def test_websocket_valid_simulation_token() -> None:
    with patch(
        "app.api.ws._verify_kiosk_exists",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with client.websocket_connect(
            "/ws/visionbox/kiosk_2",
            headers={"X-Device-Token": settings.SIMULATION_API_KEY},
        ) as websocket:
            websocket.send_json({"action": "ping"})


def test_websocket_slot_closed_event_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch(
        "app.api.ws._verify_kiosk_exists",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with caplog.at_level(logging.INFO):
            with client.websocket_connect(
                "/ws/visionbox/kiosk_3",
                headers={"X-Device-Token": settings.VISION_BOX_API_KEY},
            ) as websocket:
                websocket.send_text('{"event":"slot_closed","locker_id":"12"}')

    expected_substrings = ["slot_closed", "12"]
    matching_records = [
        record
        for record in caplog.records
        if all(substring in record.getMessage() for substring in expected_substrings)
    ]
    assert matching_records, (
        "Expected log message containing slot_closed and locker_id was not found."
    )

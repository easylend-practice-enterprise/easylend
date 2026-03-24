import asyncio

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.websockets import manager
from app.main import app

client = TestClient(app)


def test_send_command_to_connected_client() -> None:
    kiosk_id = "kiosk_send_1"

    with client.websocket_connect(
        f"/ws/visionbox/{kiosk_id}",
        headers={"X-Device-Token": settings.SIMULATION_API_KEY},
    ) as websocket:
        # Send a command from server to client
        sent = asyncio.run(
            manager.send_command(kiosk_id, {"action": "open_locker", "locker_id": "42"})
        )

        assert sent is True

        # Client should receive the JSON payload
        data = websocket.receive_json()
        assert data == {"action": "open_locker", "locker_id": "42"}

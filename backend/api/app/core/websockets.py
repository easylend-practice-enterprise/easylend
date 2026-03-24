import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, kiosk_id: str) -> None:
        await websocket.accept()
        self.active_connections[kiosk_id] = websocket
        logger.info(f"Hardware client connected: kiosk_id={kiosk_id}")

    def disconnect(self, kiosk_id: str) -> None:
        # pop() safely removes the key if it exists, returning None otherwise
        if self.active_connections.pop(kiosk_id, None) is not None:
            logger.info(f"Hardware client disconnected: kiosk_id={kiosk_id}")

    async def send_command(self, kiosk_id: str, command: dict) -> bool:
        websocket = self.active_connections.get(kiosk_id)
        if websocket:
            await websocket.send_json(command)
            return True

        logger.warning(
            f"Failed to send command. Client not online: kiosk_id={kiosk_id}"
        )
        return False


manager = ConnectionManager()

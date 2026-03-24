import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, kiosk_id: str) -> None:
        await websocket.accept()

        # If a connection for this kiosk_id already exists, close it before replacing.
        existing_websocket = self.active_connections.get(kiosk_id)
        if existing_websocket is not None and existing_websocket is not websocket:
            try:
                await existing_websocket.close()
                logger.info(
                    "Closed existing hardware client connection before reconnect: kiosk_id=%s",
                    kiosk_id,
                )
            except Exception:
                logger.exception(
                    "Error while closing existing hardware client connection: kiosk_id=%s",
                    kiosk_id,
                )

        self.active_connections[kiosk_id] = websocket
        logger.info(f"Hardware client connected: kiosk_id={kiosk_id}")

    def disconnect(self, kiosk_id: str) -> None:
        # pop() safely removes the key if it exists, returning None otherwise
        if self.active_connections.pop(kiosk_id, None) is not None:
            logger.info(f"Hardware client disconnected: kiosk_id={kiosk_id}")

    async def send_command(self, kiosk_id: str, command: dict) -> bool:
        if kiosk_id in self.active_connections:
            websocket = self.active_connections[kiosk_id]
            try:
                await websocket.send_json(command)
                return True
            except Exception:
                logger.exception(
                    "Failed to send command to kiosk_id=%s. Disconnecting.", kiosk_id
                )
                self.disconnect(kiosk_id)
                return False

        logger.warning(
            f"Failed to send command. Client not online: kiosk_id={kiosk_id}"
        )
        return False


manager = ConnectionManager()

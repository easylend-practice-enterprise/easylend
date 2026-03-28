import asyncio
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

    def disconnect(self, kiosk_id: str, websocket: WebSocket) -> None:
        # Only disconnect if this exact websocket is still the active one for kiosk_id.
        if self.active_connections.get(kiosk_id) is websocket:
            self.active_connections.pop(kiosk_id)
            logger.info(f"Hardware client disconnected: kiosk_id={kiosk_id}")

    async def send_command(self, kiosk_id: str, command: dict) -> bool:
        if kiosk_id in self.active_connections:
            websocket = self.active_connections[kiosk_id]
            try:
                # Use a short timeout to avoid blocking when the hardware TCP stack hangs.
                await asyncio.wait_for(websocket.send_json(command), timeout=3.0)
                return True
            except TimeoutError:
                logger.error("Send command to kiosk_id=%s timed out.", kiosk_id)
                try:
                    self.disconnect(kiosk_id, websocket)
                except Exception:
                    logger.exception(
                        "Error while disconnecting websocket for kiosk_id=%s",
                        kiosk_id,
                    )
                return False
            except Exception as e:
                logger.exception(
                    "Error sending command to kiosk_id=%s: %s", kiosk_id, e
                )
                try:
                    self.disconnect(kiosk_id, websocket)
                except Exception:
                    logger.exception(
                        "Error while disconnecting websocket for kiosk_id=%s",
                        kiosk_id,
                    )
                return False

        logger.warning(
            f"Failed to send command. Client not online: kiosk_id={kiosk_id}"
        )
        return False


manager = ConnectionManager()

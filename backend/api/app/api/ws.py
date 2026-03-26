import json
import logging
import secrets

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.websockets import manager

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws", tags=["websockets"])


@ws_router.websocket("/visionbox/{kiosk_id}")
async def visionbox_websocket_endpoint(
    websocket: WebSocket,
    kiosk_id: str,
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> None:
    if not x_device_token:
        logger.warning(
            f"Connection rejected: Missing X-Device-Token for kiosk_id={kiosk_id}"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    is_vision_box = secrets.compare_digest(x_device_token, settings.VISION_BOX_API_KEY)
    is_sim = secrets.compare_digest(x_device_token, settings.SIMULATION_API_KEY)

    if not (is_vision_box or is_sim):
        logger.warning(
            f"Connection rejected: Invalid X-Device-Token for kiosk_id={kiosk_id}"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Token is valid, register with the manager
    await manager.connect(websocket, kiosk_id)

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.warning(
                    f"Ignored non-JSON event from kiosk_id={kiosk_id}: {raw_message}"
                )
                continue

            logger.info(f"Received event from kiosk_id={kiosk_id}: {data}")

            if isinstance(data, dict) and data.get("event") == "slot_closed":
                locker_id = data.get("locker_id", "unknown")
                logger.info(f"Slot closed event received for locker_id={locker_id}")

    except WebSocketDisconnect:
        manager.disconnect(kiosk_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error for kiosk_id={kiosk_id}: {str(e)}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            pass
        finally:
            manager.disconnect(kiosk_id, websocket)

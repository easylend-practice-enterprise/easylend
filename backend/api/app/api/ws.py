import json
import logging
import secrets
import uuid

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.config import settings
from app.core.websockets import manager
from app.db.database import AsyncSessionLocal
from app.db.models import Locker, LockerStatus

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
                locker_id_raw = data.get("locker_id")
                logger.info(f"Slot closed event received for locker_id={locker_id_raw}")

                try:
                    locker_id = uuid.UUID(str(locker_id_raw))
                except ValueError:
                    logger.warning(
                        "Invalid UUID for slot_closed locker_id from kiosk_id=%s: %s",
                        kiosk_id,
                        locker_id_raw,
                    )
                    continue

                try:
                    async with AsyncSessionLocal() as db:
                        locker_result = await db.execute(
                            select(Locker).where(Locker.locker_id == locker_id)
                        )
                        locker = locker_result.scalar_one_or_none()
                        if locker is not None:
                            locker.locker_status = LockerStatus.OCCUPIED
                            await db.commit()
                except Exception as exc:
                    logger.exception(
                        "Failed to process slot_closed event for kiosk_id=%s: %s",
                        kiosk_id,
                        str(exc),
                    )
                    continue

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

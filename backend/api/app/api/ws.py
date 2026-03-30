import json
import logging
import secrets

from fastapi import APIRouter, Depends, Header, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.websockets import manager
from app.db.database import get_db
from app.db.models import Kiosk

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws", tags=["websockets"])


async def _verify_kiosk_exists(db: AsyncSession, kiosk_id: str) -> bool:
    """Return True only when kiosk_id is a valid UUID that exists in the DB."""
    try:
        from uuid import UUID

        parsed = UUID(kiosk_id)
    except (ValueError, AttributeError):
        return False
    result = await db.execute(select(Kiosk.kiosk_id).where(Kiosk.kiosk_id == parsed))
    return result.scalar_one_or_none() is not None


@ws_router.websocket("/visionbox/{kiosk_id}")
async def visionbox_websocket_endpoint(
    websocket: WebSocket,
    kiosk_id: str,
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    db: AsyncSession = Depends(get_db),
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

    # Enforce that the kiosk_id is a known kiosk in the DB (prevents kiosk impersonation).
    if not await _verify_kiosk_exists(db, kiosk_id):
        logger.warning(
            "Connection rejected: kiosk_id=%s is not registered in the database.",
            kiosk_id,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Token valid and kiosk registered — register with the manager
    await manager.connect(websocket, kiosk_id)

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                safe_msg = str(raw_message).replace("\n", " ").replace("\r", "")[:200]
                logger.warning(
                    "Ignored non-JSON event from kiosk_id=%s: %s", kiosk_id, safe_msg
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
            logger.debug("WebSocket close failed: client already disconnected.")
        finally:
            manager.disconnect(kiosk_id, websocket)

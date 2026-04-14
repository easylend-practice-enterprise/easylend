import asyncio
import inspect
import json
import logging
from typing import Any

from fastapi import WebSocket
from redis.exceptions import RedisError

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

MAX_CONNECTIONS = 100
PRESENCE_TTL_SECONDS = 30
PRESENCE_REFRESH_SECONDS = 10
COMMAND_SEND_TIMEOUT_SECONDS = 3.0
PUBSUB_POLL_TIMEOUT_SECONDS = 1.0


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self._presence_tasks: dict[str, asyncio.Task[None]] = {}
        self._command_tasks: dict[str, asyncio.Task[None]] = {}
        self._pubsubs: dict[str, Any] = {}

    def _presence_key(self, kiosk_id: str) -> str:
        return f"kiosk:presence:{kiosk_id}"

    def _command_channel(self, kiosk_id: str) -> str:
        return f"kiosk:commands:{kiosk_id}"

    async def _set_presence(self, kiosk_id: str) -> None:
        try:
            await redis_client.set(
                self._presence_key(kiosk_id),
                "online",
                ex=PRESENCE_TTL_SECONDS,
            )
        except RedisError:
            logger.warning(
                "Failed to set kiosk presence in Redis for kiosk_id=%s",
                kiosk_id,
            )

    async def _clear_presence(self, kiosk_id: str) -> None:
        try:
            await redis_client.delete(self._presence_key(kiosk_id))
        except RedisError:
            logger.warning(
                "Failed to clear kiosk presence in Redis for kiosk_id=%s",
                kiosk_id,
            )

    async def _cancel_task(self, task: asyncio.Task[None] | None) -> None:
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _aclose_pubsub(self, pubsub: Any) -> None:
        close_method = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
        if close_method is None:
            return
        result = close_method()
        if inspect.isawaitable(result):
            await result

    async def _close_pubsub(self, kiosk_id: str) -> None:
        pubsub = self._pubsubs.pop(kiosk_id, None)
        if pubsub is None:
            return

        channel = self._command_channel(kiosk_id)
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            logger.exception(
                "Failed to unsubscribe Redis command channel for kiosk_id=%s",
                kiosk_id,
            )

        try:
            await self._aclose_pubsub(pubsub)
        except Exception:
            logger.exception(
                "Failed to close Redis pubsub client for kiosk_id=%s",
                kiosk_id,
            )

    async def _presence_heartbeat(self, kiosk_id: str, websocket: WebSocket) -> None:
        try:
            while self.active_connections.get(kiosk_id) is websocket:
                await self._set_presence(kiosk_id)
                await asyncio.sleep(PRESENCE_REFRESH_SECONDS)
        except asyncio.CancelledError:
            raise

    async def _forward_commands(self, kiosk_id: str, websocket: WebSocket) -> None:
        pubsub = self._pubsubs.get(kiosk_id)
        if pubsub is None:
            return

        while self.active_connections.get(kiosk_id) is websocket:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=PUBSUB_POLL_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                raise
            except RedisError:
                logger.exception(
                    "Redis Pub/Sub listener failed for kiosk_id=%s",
                    kiosk_id,
                )
                await self.disconnect(kiosk_id, websocket, close_websocket=True)
                return

            if message is None:
                await asyncio.sleep(0.05)
                continue

            raw_payload = message.get("data")
            if isinstance(raw_payload, bytes):
                raw_payload = raw_payload.decode("utf-8", errors="ignore")
            if not isinstance(raw_payload, str):
                logger.warning(
                    "Ignoring non-string command payload for kiosk_id=%s",
                    kiosk_id,
                )
                continue

            try:
                command = json.loads(raw_payload)
            except json.JSONDecodeError:
                logger.warning(
                    "Ignoring malformed command payload for kiosk_id=%s",
                    kiosk_id,
                )
                continue

            try:
                await asyncio.wait_for(
                    websocket.send_json(command),
                    timeout=COMMAND_SEND_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:  # noqa: UP041
                logger.error(
                    "Forwarding command to kiosk websocket timed out for kiosk_id=%s",
                    kiosk_id,
                )
                await self.disconnect(kiosk_id, websocket, close_websocket=True)
                return
            except Exception:
                logger.exception(
                    "Failed to forward command to kiosk websocket for kiosk_id=%s",
                    kiosk_id,
                )
                await self.disconnect(kiosk_id, websocket, close_websocket=True)
                return

    async def connect(self, websocket: WebSocket, kiosk_id: str) -> bool:
        # Global connection cap to prevent memory / fd exhaustion.
        if len(self.active_connections) >= MAX_CONNECTIONS:
            logger.warning(
                "Connection rejected: global connection limit reached (MAX_CONNECTIONS=%d)",
                MAX_CONNECTIONS,
            )
            await websocket.close(code=1013, reason="Connection limit reached")
            return False

        # Subscribe to the Redis pubsub channel BEFORE accepting the WebSocket.
        # If this succeeds but websocket.accept() fails below, the pubsub is
        # registered in self._pubsubs and will be cleaned up by _close_pubsub.
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(self._command_channel(kiosk_id))
            self._pubsubs[kiosk_id] = pubsub
        except RedisError:
            logger.exception(
                "Connection rejected: unable to subscribe Redis command channel for kiosk_id=%s",
                kiosk_id,
            )
            await websocket.close(code=1011, reason="Command channel unavailable")
            return False

        # If a connection for this kiosk_id already exists, close it before replacing.
        existing_websocket = self.active_connections.get(kiosk_id)
        if existing_websocket is not None and existing_websocket is not websocket:
            try:
                await self.disconnect(
                    kiosk_id,
                    existing_websocket,
                    close_websocket=True,
                )
                logger.info(
                    "Closed existing hardware client connection before reconnect: kiosk_id=%s",
                    kiosk_id,
                )
            except Exception:
                logger.exception(
                    "Error while closing existing hardware client connection: kiosk_id=%s",
                    kiosk_id,
                )

        try:
            await websocket.accept()
        except Exception:
            # accept failed — clean up the pubsub that was registered above.
            await self._close_pubsub(kiosk_id)
            raise

        self.active_connections[kiosk_id] = websocket
        await self._set_presence(kiosk_id)

        self._presence_tasks[kiosk_id] = asyncio.create_task(
            self._presence_heartbeat(kiosk_id, websocket),
            name=f"presence-heartbeat-{kiosk_id}",
        )
        self._command_tasks[kiosk_id] = asyncio.create_task(
            self._forward_commands(kiosk_id, websocket),
            name=f"command-forwarder-{kiosk_id}",
        )

        logger.info("Hardware client connected: kiosk_id=%s", kiosk_id)
        return True

    async def disconnect(
        self,
        kiosk_id: str,
        websocket: WebSocket,
        *,
        close_websocket: bool = False,
    ) -> None:
        if close_websocket:
            try:
                await websocket.close()
            except Exception:  # noqa: S110
                pass

        # Only disconnect if this exact websocket is still the active one for kiosk_id.
        if self.active_connections.get(kiosk_id) is not websocket:
            return

        self.active_connections.pop(kiosk_id, None)
        await self._clear_presence(kiosk_id)

        presence_task = self._presence_tasks.pop(kiosk_id, None)
        command_task = self._command_tasks.pop(kiosk_id, None)

        await self._cancel_task(presence_task)
        await self._cancel_task(command_task)
        await self._close_pubsub(kiosk_id)

        logger.info("Hardware client disconnected: kiosk_id=%s", kiosk_id)

    async def is_kiosk_online(self, kiosk_id: str) -> bool:
        if kiosk_id in self.active_connections:
            return True

        try:
            return (await redis_client.exists(self._presence_key(kiosk_id))) > 0
        except RedisError:
            logger.warning(
                "Redis unavailable while checking kiosk presence for kiosk_id=%s",
                kiosk_id,
            )
            return kiosk_id in self.active_connections

    async def send_command(self, kiosk_id: str, command: dict) -> bool:
        channel = self._command_channel(kiosk_id)

        websocket = self.active_connections.get(kiosk_id)
        if websocket:
            try:
                await asyncio.wait_for(
                    websocket.send_json(command),
                    timeout=COMMAND_SEND_TIMEOUT_SECONDS,
                )
                return True
            except Exception:
                logger.debug(
                    "Local websocket send failed; falling back to Redis for kiosk_id=%s",
                    kiosk_id,
                    exc_info=True,
                )

        try:
            payload = json.dumps(command, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            logger.exception(
                "Failed to serialize command payload for kiosk_id=%s",
                kiosk_id,
            )
            return False

        try:
            subscribers = await redis_client.publish(channel, payload)
        except RedisError:
            logger.exception(
                "Failed to publish command to Redis for kiosk_id=%s",
                kiosk_id,
            )
            return False

        if subscribers <= 0:
            logger.warning(
                "Command publish had no subscribers for kiosk_id=%s",
                kiosk_id,
            )
            return False

        return True


manager = ConnectionManager()

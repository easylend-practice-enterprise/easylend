import asyncio
import json
import logging
import os
from collections.abc import Callable
from typing import Any

import httpx
import websockets
from PIL import Image
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class DigitalTwin:
    def __init__(self, ws_url: str, analyze_url: str, device_token: str):
        self.ws_url = ws_url
        self.analyze_url = analyze_url
        self.device_token = device_token

        self.slot_open = False
        self.led_status = "off"
        self.helderheid = 0.0

        self.current_loan_id: str | None = None
        self.current_eval_type: str | None = None

        self.ws: Any = None
        self.on_state_change: Callable[[str], Any] | None = None
        self.image_path = "test_image.jpg"

    async def connect(self):
        """Maintains the connection to the EasyLend backend."""
        headers = {"X-Device-Token": self.device_token}
        attempt = 0

        while True:
            try:
                attempt = 0
                if self.on_state_change:
                    await self.on_state_change("sys:Connecting...")
                async with websockets.connect(
                    self.ws_url, additional_headers=headers
                ) as ws:
                    logger.info(f"Connected to backend at {self.ws_url}")
                    if self.on_state_change:
                        await self.on_state_change("sys:Connected to backend")
                    self.ws = ws
                    await self._listen()
            except (ConnectionClosed, Exception) as e:
                attempt += 1
                backoff = min(0.1 * (2**attempt), 30.0)
                logger.error(f"WebSocket error: {e}. Retrying in {backoff:.1f}s...")
                if self.on_state_change:
                    await self.on_state_change(f"sys:error: {str(e)[:40]}")
                self.ws = None
                await asyncio.sleep(backoff)

    async def _listen(self):
        """Internal loop to process commands from the backend."""
        async for message in self.ws:
            try:
                data = json.loads(message)
                action = data.get("action")
                logger.info(f"Received command: {action}")

                if self.on_state_change:
                    await self.on_state_change(f"cmd:{json.dumps(data)}")

                if action == "set_led":
                    color = data.get("color", "green")
                    self.led_status = color
                    self.helderheid = 1.0
                    if self.on_state_change:
                        await self.on_state_change("update")

                elif action == "open_slot":
                    self.slot_open = True
                    self.current_loan_id = data.get("loan_id")
                    self.current_eval_type = data.get("evaluation_type")
                    if self.on_state_change:
                        await self.on_state_change("update")

            except Exception as e:
                logger.error(f"Failed to process message: {e}")

    async def close_slot(self):
        """Simulates closing the door and triggers AI analysis."""
        self.slot_open = False
        if self.on_state_change:
            await self.on_state_change("update")

        if self.ws:
            msg = {
                "event": "slot_closed",
                "locker_id": "1",
                "loan_id": self.current_loan_id,
                "evaluation_type": self.current_eval_type,
            }
            await self.ws.send(json.dumps(msg))
            logger.info("Sent 'slot_closed' to backend: %s", msg)

        if self.current_loan_id and self.current_eval_type:
            # Fire-and-forget: log completion/error via task
            async def log_upload():
                try:
                    await self._upload_image()
                    logger.info(
                        "Background upload completed for loan %s", self.current_loan_id
                    )
                except Exception as e:
                    logger.error(
                        "Background upload failed for loan %s: %s",
                        self.current_loan_id,
                        e,
                    )

            asyncio.create_task(log_upload())

    async def _upload_image(self):
        """Simulates camera capture and upload."""
        if not os.path.exists(self.image_path):
            img = Image.new("RGB", (640, 480), color=(100, 150, 200))
            img.save(self.image_path)

        logger.info(f"Uploading image for loan {self.current_loan_id}...")

        headers = {"X-Device-Token": self.device_token}
        data = {
            "loan_id": self.current_loan_id,
            "evaluation_type": self.current_eval_type,
        }

        async with httpx.AsyncClient() as client:
            try:
                with open(self.image_path, "rb") as f:
                    files = {"file": ("snapshot.jpg", f, "image/jpeg")}
                    resp = await client.post(
                        self.analyze_url,
                        headers=headers,
                        data=data,
                        files=files,
                        timeout=30.0,
                    )
                logger.info(f"AI Response: {resp.status_code}")
            except Exception as e:
                logger.error(f"Image upload failed: {e}")
            finally:
                self.current_loan_id = None
                self.current_eval_type = None

    def get_state(self):
        return {
            "slot_open": self.slot_open,
            "led_aan": self.led_status != "off",
            "led_color": self.led_status,
            "helderheid": self.helderheid,
            "microswitch": not self.slot_open,
        }

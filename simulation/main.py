import asyncio
import json
import logging
import os

import websockets
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed, WebSocketException

# Initialize logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load variables from .env (if present)
load_dotenv()

API_URL = os.environ.get(
    "VISIONBOX_WS_URL", "ws://localhost:8000/ws/visionbox/kiosk_sim_1"
)
# Prefer an environment-provided simulation API key to match the backend's .env
DEVICE_TOKEN = os.environ.get("SIMULATION_API_KEY", "local-dev-sim-key-123")  # noqa: S105


async def run_client() -> None:
    headers = [("X-Device-Token", DEVICE_TOKEN)]

    try:
        async with websockets.connect(API_URL, additional_headers=headers) as ws:
            logger.info("Connected to backend WebSocket.")

            payload = {"action": "slot_closed", "locker_id": "123"}
            await ws.send(json.dumps(payload))
            logger.info(f"Sent payload: {payload}")

            while True:
                message = await ws.recv()
                logger.info(f"Received payload: {message}")

    except ConnectionClosed as e:
        logger.error(f"Connection closed. Code: {e.code}, Reason: {e.reason}")
    except WebSocketException as e:
        logger.error(f"WebSocket protocol error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        logger.info("Simulation stopped by user.")

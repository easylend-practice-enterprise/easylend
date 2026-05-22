import asyncio
import json
import logging
import os

import httpx
import websockets
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed, WebSocketException

# Initialize logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load variables from .env
load_dotenv()

# Configuration
WS_URL = os.environ.get(
    "VISIONBOX_WS_URL",
    "ws://localhost:8000/ws/visionbox/00000000-0000-0000-0000-000000000000",
)
REST_API_URL = os.environ.get(
    "VISION_ANALYZE_URL", "http://localhost:8000/api/v1/vision/analyze"
)
DEVICE_TOKEN = os.environ.get("SIMULATION_API_KEY", "local-dev-sim-key-123")
IMAGE_PATH = "test_image.jpg"


async def upload_image_to_ai(loan_id: str, evaluation_type: str) -> None:
    """Simulates the hardware camera taking a picture and uploading it to the backend."""
    if not os.path.exists(IMAGE_PATH):
        logger.error(
            f"Image not found at '{IMAGE_PATH}'. Please create a dummy image to simulate the camera."
        )
        return

    logger.info(
        f"📸 Uploading image for loan {loan_id} ({evaluation_type}) to Real API..."
    )

    headers = {"X-Device-Token": DEVICE_TOKEN}
    data = {"loan_id": loan_id, "evaluation_type": evaluation_type}

    async with httpx.AsyncClient() as client:
        try:
            with open(IMAGE_PATH, "rb") as f:
                files = {"file": ("snapshot.jpg", f, "image/jpeg")}
                response = await client.post(
                    REST_API_URL,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=60.0,  # AI inference can take a while
                )

            logger.info(f"✅ API Response [{response.status_code}]: {response.text}")
        except Exception as e:
            logger.error(f"❌ Failed to upload image: {e}")


async def run_client() -> None:
    headers = [("X-Device-Token", DEVICE_TOKEN)]

    try:
        async with websockets.connect(WS_URL, additional_headers=headers) as ws:
            logger.info("🔗 Connected to EasyLend Backend WebSocket.")
            logger.info("🎧 Listening for hardware commands...")

            async for message in ws:
                data = json.loads(message)
                action = data.get("action")

                if action == "set_led":
                    locker = data.get("locker_id")
                    color = data.get("color")
                    logger.info(f"💡 LED EVENT: Locker {locker} turned {color.upper()}")

                elif action == "open_slot":
                    locker_id = data.get("locker_id")
                    loan_id = data.get("loan_id")
                    eval_type = data.get("evaluation_type")

                    logger.info(
                        f"🔓 DOOR EVENT: Opened locker {locker_id} for {eval_type}."
                    )

                    # 1. Simulate the time it takes for a user to grab/return an item
                    logger.info("⏳ Simulating user interaction... (waiting 4 seconds)")
                    await asyncio.sleep(4)

                    # 2. Simulate the door closing
                    logger.info(
                        f"🚪 SENSOR EVENT: Locker {locker_id} door closed manually."
                    )
                    await ws.send(
                        json.dumps(
                            {"event": "slot_closed", "locker_id": str(locker_id)}
                        )
                    )

                    # 3. If a loan is active, trigger the camera & AI upload in the background
                    if loan_id and eval_type:
                        asyncio.create_task(upload_image_to_ai(loan_id, eval_type))

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

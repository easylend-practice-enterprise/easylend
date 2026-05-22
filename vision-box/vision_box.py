import io
import json
import os
import threading
import time
import uuid

import requests
import websocket
from gpiozero import PWMLED, Button, DigitalOutputDevice
from picamera2 import Picamera2
from PIL import Image

# ==============================================================================
# 1. Configuration
# ==============================================================================
BACKEND_HOST = "192.168.1.229:8000"
VISION_BOX_API_KEY = "YOUR_STATIC_VISION_BOX_API_KEY_HERE"

WSS_URL = f"ws://{BACKEND_HOST}/ws/vision"
POST_URL = f"http://{BACKEND_HOST}/api/v1/vision/analyze"

HEADERS = {"X-Device-Token": VISION_BOX_API_KEY}

# Queue Configuration
QUEUE_DIR = "payload_queue"
QUEUE_RETRY_INTERVAL = 15  # Seconds between retry attempts

# Ensure queue directory exists on startup
os.makedirs(QUEUE_DIR, exist_ok=True)

# ==============================================================================
# 2. Hardware Allocation
# ==============================================================================
lock_trigger = DigitalOutputDevice(24)
lock_sensor = Button(23)
led_strip = PWMLED(18, frequency=2000)

# ==============================================================================
# 3. Global State Management
# ==============================================================================
transaction_context = {
    "loan_id": None,
    "evaluation_type": None,
    "is_active_session": False,
}
ws_client = None

# ==============================================================================
# 4. Camera Initialization
# ==============================================================================
print("Initializing IMX708 camera interface...")
picam2 = Picamera2()
config = picam2.create_video_configuration(main={"size": (2304, 1296)})
picam2.configure(config)
picam2.set_controls(
    {
        "AfMode": 2,  # Continuous autofocus
        "AeConstraintMode": 3,  # Noise suppression profile
        "AnalogueGain": 2.0,  # Fixed analog gain to minimize thermal noise
    }
)
picam2.start()
print("Camera initialized.")

# ==============================================================================
# 5. Lighting Control
# ==============================================================================
CIE_TABLE = [((L / 903.3) if L <= 8 else ((L + 16) / 116) ** 3) for L in range(101)]


def set_led_brightness(percent):
    idx = max(0, min(100, int(percent)))
    led_strip.value = CIE_TABLE[idx]


def status_secured():
    set_led_brightness(10)


def status_attention():
    set_led_brightness(40)


def status_illuminated():
    set_led_brightness(100)


# ==============================================================================
# 6. Image Capture and Validation
# ==============================================================================
def capture_and_validate_frame():
    print("Initiating focus sweep and capturing frame...")
    try:
        picam2.set_controls({"AfMode": 1})
        picam2.set_controls({"AfTrigger": 1})
        time.sleep(0.5)

        frame_data = picam2.capture_array(name="main")
        picam2.set_controls({"AfMode": 2})

        img = Image.fromarray(frame_data)
        if img.mode != "RGB":
            img = img.convert("RGB")

        jpeg_buffer = io.BytesIO()
        img.save(jpeg_buffer, format="JPEG", quality=95)
        raw_bytes = jpeg_buffer.getvalue()

        gray_img = img.convert("L")
        _ = gray_img.getextrema()

        pixels = list(gray_img.getdata())
        avg_brightness = sum(pixels) / len(pixels)
        print(f"Validation result - Avg Brightness: {avg_brightness:.2f} Luma units")

        if 40.0 <= avg_brightness <= 245.0:
            return raw_bytes, True

        return raw_bytes, False
    except Exception as e:
        print(f"Frame processing failed: {e}")
        return None, False


def edge_validation_loop():
    start_time = time.time()
    timeout = 5.0
    retry_count = 1

    status_illuminated()
    time.sleep(0.2)

    while time.time() - start_time < timeout:
        print(f"Capture attempt: #{retry_count}")
        frame, is_valid = capture_and_validate_frame()

        if is_valid and frame:
            print("Validation passed. Frame acquired.")
            status_secured()
            return frame

        print("Frame validation failed. Retrying...")
        retry_count += 1
        time.sleep(0.1)

    print("Timeout: Unable to capture a valid frame within 5 seconds.")
    status_attention()
    return None


# ==============================================================================
# 7. Local Payload Queuing System
# ==============================================================================
def enqueue_payload(image_bytes, payload_data):
    """Writes the image and metadata to local disk for later transmission."""
    transaction_id = str(uuid.uuid4())
    img_path = os.path.join(QUEUE_DIR, f"{transaction_id}.jpg")
    json_path = os.path.join(QUEUE_DIR, f"{transaction_id}.json")

    try:
        with open(img_path, "wb") as f:
            f.write(image_bytes)

        with open(json_path, "w") as f:
            json.dump(payload_data, f)

        print(f"Payload enqueued locally. Transaction ID: {transaction_id}")
    except Exception as e:
        print(f"CRITICAL: Failed to write payload to local disk: {e}")


def process_queue_worker():
    """Background thread that continuously attempts to flush the local queue."""
    while True:
        time.sleep(QUEUE_RETRY_INTERVAL)

        # Find all queued metadata files
        queued_files = [f for f in os.listdir(QUEUE_DIR) if f.endswith(".json")]

        if not queued_files:
            continue

        print(
            f"Queue Worker: Found {len(queued_files)} pending payloads. Attempting transmission..."
        )

        for json_file in queued_files:
            transaction_id = json_file.replace(".json", "")
            json_path = os.path.join(QUEUE_DIR, json_file)
            img_path = os.path.join(QUEUE_DIR, f"{transaction_id}.jpg")

            if not os.path.exists(img_path):
                print(f"Queue Worker: Orphaned JSON found ({json_file}). Removing.")
                os.remove(json_path)
                continue

            # Load payload data
            try:
                with open(json_path) as f:
                    payload = json.load(f)
                with open(img_path, "rb") as f:
                    image_bytes = f.read()
            except Exception as e:
                print(f"Queue Worker: Failed to read transaction {transaction_id}: {e}")
                continue

            # Attempt Transmission
            files = {"file": ("capture.jpg", image_bytes, "image/jpeg")}
            try:
                response = requests.post(
                    POST_URL, headers=HEADERS, data=payload, files=files, timeout=10
                )
                if response.status_code == 200:
                    print(f"Queue Worker: Successfully transmitted {transaction_id}.")
                    # Clean up local files upon success
                    os.remove(json_path)
                    os.remove(img_path)
                else:
                    print(
                        f"Queue Worker: Backend rejected {transaction_id} ({response.status_code}). Aborting queue flush."
                    )
                    status_attention()
                    break  # Stop processing the queue until the next interval

            except Exception as e:
                print(f"Queue Worker: Network unavailable ({e}). Aborting queue flush.")
                status_attention()
                break  # Stop processing the queue until the next interval


def transmit_payload_to_backend(image_bytes):
    """Attempts immediate upload. Routes to queue on failure."""
    if not image_bytes:
        print("Transmission aborted: Image buffer is empty.")
        return

    payload = {
        "loan_id": transaction_context["loan_id"],
        "evaluation_type": transaction_context["evaluation_type"],
    }

    files = {"file": ("capture.jpg", image_bytes, "image/jpeg")}
    print(f"Attempting payload transmission to {POST_URL}...")

    try:
        response = requests.post(
            POST_URL, headers=HEADERS, data=payload, files=files, timeout=10
        )
        if response.status_code == 200:
            print("Payload successfully accepted by backend.")
        else:
            print(f"Backend rejected payload: {response.status_code} - {response.text}")
            print("Routing to local queue.")
            enqueue_payload(image_bytes, payload)
            status_attention()
    except Exception as e:
        print(f"Connection to backend failed: {e}")
        print("Routing to local queue.")
        enqueue_payload(image_bytes, payload)
        status_attention()


# ==============================================================================
# 8. Hardware Interrupt Handlers
# ==============================================================================
def on_physical_door_closed():
    if not transaction_context["is_active_session"]:
        return

    print("\nDoor closed event detected. Freezing session state.")
    transaction_context["is_active_session"] = False

    if ws_client:
        try:
            ws_client.send(json.dumps({"event": "slot_closed"}))
        except Exception as e:
            print(f"WebSocket notification failed (payload will queue): {e}")

    def process_transaction():
        valid_frame = edge_validation_loop()
        if valid_frame:
            transmit_payload_to_backend(valid_frame)
        else:
            print("Alerting administrator: Validation fallback logic triggered.")

    threading.Thread(target=process_transaction, daemon=True).start()


lock_sensor.when_released = on_physical_door_closed


# ==============================================================================
# 9. WebSocket Event Handlers
# ==============================================================================
def on_message(ws, message):
    print(f"\nIncoming WebSocket message: {message}")
    try:
        data = json.loads(message)
        command = data.get("command")

        if command == "open_slot":
            transaction_context["loan_id"] = data["loan_id"]
            transaction_context["evaluation_type"] = data["evaluation_type"]
            transaction_context["is_active_session"] = True

            print(
                f"Command verified. Opening lock for Loan ID: {transaction_context['loan_id']}"
            )
            lock_trigger.on()
            time.sleep(1.5)
            lock_trigger.off()

        elif command == "set_led":
            color = data.get("color", "").upper()
            print(f"Illumination adjustment requested: {color}")
            if color == "GREEN":
                set_led_brightness(100)
            elif color == "RED":
                set_led_brightness(0)
            elif color == "ORANGE":
                set_led_brightness(40)
    except Exception as e:
        print(f"Error processing WebSocket payload: {e}")


def on_error(ws, error):
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    print("WebSocket connection closed. Attempting to reconnect...")
    time.sleep(3.0)
    connect_websocket_session()


def on_open(ws):
    print("WebSocket connection established.")
    status_secured()


def connect_websocket_session():
    global ws_client
    ws_client = websocket.WebSocketApp(
        WSS_URL,
        header=[f"X-Device-Token: {VISION_BOX_API_KEY}"],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    # Ping interval added to keep TCP connection alive through NAT/Proxies
    wst = threading.Thread(
        target=ws_client.run_forever, kwargs={"ping_interval": 30, "ping_timeout": 10}
    )
    wst.daemon = True
    wst.start()


# ==============================================================================
# 10. Main Execution
# ==============================================================================
if __name__ == "__main__":
    print("\n=======================================================")
    print("               EASYLEND VISION BOX CLIENT              ")
    print("=======================================================")

    # Initialize background worker for payload queue
    queue_thread = threading.Thread(target=process_queue_worker, daemon=True)
    queue_thread.start()
    print("Background queue worker initialized.")

    status_secured()
    connect_websocket_session()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down hardware outputs safely...")
        led_strip.off()
        lock_trigger.off()

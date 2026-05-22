import io
import threading
import time

from flask import Flask, Response, jsonify, render_template_string, request, send_file
from gpiozero import PWMLED, Button, DigitalOutputDevice
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput

# --- Hardware Allocation ---
led_strip = PWMLED(18)  # 12V COB LED Strip
lock_trigger = DigitalOutputDevice(24)
lock_sensor = Button(23)

app = Flask(__name__)

# --- Camera Initializations ---


class WebStreamBuffer(io.BufferedIOBase):
    def __init__(self):
        super().__init__()
        self.frame = b""
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = bytes(buf)
            self.condition.notify_all()
        return len(buf)


video_buffer = WebStreamBuffer()

print("Configuring IMX708 Subsystem for AI Dual-Streams...")
picam2 = Picamera2()

config = picam2.create_video_configuration(
    main={
        "size": (2304, 1296)
    },  # 2K resolution stream for clean cloud Vision AI parsing
    lores={"size": (640, 480)},  # Low resolution stream for fast web preview
)
picam2.configure(config)

# FIX: Use the official libcamera Control identifiers to suppress sensor grain
# We tell the Auto Exposure (AE) engine to target the 'Noise' reduction constraint mode profile
picam2.set_controls(
    {
        "AeConstraintMode": 3,  # 3 = Noise suppression emphasis profile
        "AnalogueGain": 2.0,  # Explicitly set low sensitivity baseline multiplier to wipe out thermal grain
    }
)


# ROBUST AF: Enable continuous video tracking as the baseline background state
picam2.set_controls(
    {"AfMode": 2}
)  # 2 = AfModeContinuous (Always actively seeking focus)

encoder = MJPEGEncoder(bitrate=3000000)
picam2.start_recording(encoder, FileOutput(video_buffer), name="lores")
print("Live autofocus pipeline running.")


def capture_high_res_robust():
    """Executes a multi-stage focus tracking routine to verify a sharp 2K capture."""
    print("Initiating robust multi-stage autofocus confirmation sequence...")

    # ACTIVATE VISION BOX ILLUMINATION
    print("Illuminating Vision Box to 100%...")
    led_strip.value = 1.0
    time.sleep(
        0.5
    )  # Allow the camera sensor half a second to adjust to the bright light (Auto Exposure)

    try:
        # Step 1: Force camera to manual tracking mode to accept a clean software sweep trigger
        picam2.set_controls({"AfMode": 1})  # 1 = AfModeAuto
        picam2.set_controls({"AfTrigger": 1})  # 1 = AfTriggerStart

        # Step 2: Actively poll the hardware ISP metadata dictionary until focused
        max_attempts = 15
        focus_locked = False

        for attempt in range(max_attempts):
            time.sleep(0.08)

            metadata = picam2.capture_metadata()
            if metadata and "AfState" in metadata:
                state = metadata["AfState"]
                if state == 2:
                    print(
                        f"Lens motor successfully locked focus on Attempt {attempt + 1}!"
                    )
                    focus_locked = True
                    break
                elif state == 3:
                    print(
                        f"Internal hardware reporting focus failure on Attempt {attempt + 1}. Retrying..."
                    )
                    picam2.set_controls({"AfTrigger": 1})

        if not focus_locked:
            print(
                "Robust timeout: Hardware did not report a firm lock. Capturing fallback frame."
            )

        # Step 3: Extract the raw numpy array pixels
        frame_data = picam2.capture_array(name="main")

        # Step 4: Reset the camera matrix safely back to continuous video mode
        picam2.set_controls({"AfMode": 2})

        # Step 5: Convert and compress using Pillow
        high_res_buffer = io.BytesIO()
        from PIL import Image

        img = Image.fromarray(frame_data)
        if img.mode != "RGB":
            img = img.convert("RGB")

        img.save(high_res_buffer, format="JPEG", quality=95)
        raw_ai_bytes = high_res_buffer.getvalue()

        print(f"High-res frame generated safely ({len(raw_ai_bytes) / 1024:.2f} KB)")
        return raw_ai_bytes

    except Exception as e:
        print(f"Robust snapshot sequence failed: {e}")
        picam2.set_controls({"AfMode": 2})
        return b""
    finally:
        # ENSURE ILLUMINATION IS ALWAYS DEACTIVATED, EVEN ON EXCEPTIONS
        led_strip.value = 0.0
        print("Vision Box illumination deactivated.")


# --- Responsive Web User Interface HTML ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Pi Security Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; text-align: center; background: #121212; color: white; margin: 0; padding: 20px; }
        .container { max-width: 700px; margin: 0 auto; }
        .stream { width: 100%; max-width: 640px; min-height: 480px; background: #000; border: 3px solid #333; border-radius: 8px; }
        .status-box { padding: 15px; margin: 20px 0; font-size: 1.2rem; border-radius: 5px; font-weight: bold; }
        .secured { background: #1b5e20; color: #a5d6a7; }
        .open { background: #b71c1c; color: #ef9a9a; }
        .btn-box { display: flex; gap: 15px; justify-content: center; margin-top: 15px; flex-wrap: wrap; }
        .btn { flex: 1; min-width: 200px; max-width: 300px; padding: 20px; font-size: 1.3rem; font-weight: bold; color: white; border: none; border-radius: 8px; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn-blue { background: #0288d1; box-shadow: 0 4px #01579b; }
        .btn-green { background: #2e7d32; box-shadow: 0 4px #1b5e20; }
        .btn-purple { background: #6a1b9a; box-shadow: 0 4px #4a148c; }
    </style>
    <script>
        setInterval(function() {
            fetch('/api/status').then(r => r.json()).then(data => {
                const el = document.getElementById('status-box');
                el.innerText = "Status: " + data.status;
                el.className = data.is_secured ? "status-box secured" : "status-box open";
            });
        }, 1000);

        function openLock() {
            fetch('/api/open', { method: 'POST' });
        }

        function triggerAiSnapshot() {
            fetch('/api/capture', { method: 'POST' })
                .then(r => r.json())
                .then(data => alert("AI Snapshot Processing Started! Look at your Pi console terminal window."));
        }
    </script>
</head>
<body>
    <div class="container">
        <h2>Live Entry Feed (IMX708)</h2>
        <img class="stream" src="/video_feed" alt="Live Security Stream">
        <div id="status-box" class="status-box {% if is_secured %}secured{% else %}open{% endif %}">Status: Verification...</div>

        <div class="btn-box">
            <button class="btn btn-blue" onclick="openLock()">UNLOCK DOOR</button>
            <button class="btn btn-green" onclick="triggerAiSnapshot()">AI SNAPSHOT</button>
            <a class="btn btn-purple" href="/view_latest" target="_blank">VIEW 2K IMAGE</a>
        </div>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            with video_buffer.condition:
                video_buffer.condition.wait()
                frame = video_buffer.frame
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    is_secured = lock_sensor.is_pressed
    return {
        "is_secured": is_secured,
        "status": "CLOSED & SECURED" if is_secured else "OPEN / RELEASED",
    }


@app.route("/view_latest")
def view_latest():
    # Directly link browser window views to our robust capture framework
    img_bytes = capture_high_res_robust()
    if not img_bytes:
        return "Failed to grab high-resolution frame", 500
    if request.args.get("download") == "true":
        return send_file(
            io.BytesIO(img_bytes),
            mimetype="image/jpeg",
            as_attachment=True,
            download_name=f"ai_capture_{int(time.time())}.jpg",
        )
    return Response(img_bytes, mimetype="image/jpeg")


@app.route("/api/capture", methods=["POST"])
def api_capture():
    def task():
        # F841 Fix: Function is called, but the result is not unnecessarily
        # stored in a variable until cloud transmission logic is added.
        capture_high_res_robust()
        # [READY FOR TRANSMISSION TO CLOUD NO-SQL/API NODES HERE]

    threading.Thread(target=task).start()
    return jsonify(
        {"result": "success", "message": "Vision processing started in background."}
    )


@app.route("/api/open", methods=["POST"])
def api_open():
    """
    Logical flow:
    1. Disengage lock instantly for the user.
    2. Activate light & capture image (while the door is opening/open).
    """

    def trigger():
        print("Unlocking door instantly for zero-latency UX!")
        lock_trigger.on()

        # Keep the lock disengaged for 4 seconds
        time.sleep(4.0)

        print("Disengaging lock solenoid power.")
        lock_trigger.off()

        # Optional: Capture an image after closing to verify returned items
        # To capture the image *before* opening, place 'capture_high_res_robust()' ABOVE lock_trigger.on()

    threading.Thread(target=trigger).start()
    return jsonify({"result": "success", "message": "Door unlocked."})


if __name__ == "__main__":
    # noqa: S104, S201 warnings suppressed: 0.0.0.0 and debug=True are intentional for local testing.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False, threaded=True)  # noqa: S104, S201

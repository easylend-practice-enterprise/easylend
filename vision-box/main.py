import asyncio
import json
import time

import cv2
import numpy as np
import requests
import websockets

# --- HARDWARE COMPATIBILITEIT ---
try:
    import RPi.GPIO as GPIO

    HAS_HARDWARE = True
except (ImportError, RuntimeError):
    HAS_HARDWARE = False
    print(
        "Systeemmelding: Geen Raspberry Pi hardware gedetecteerd. Simulatie-modus actief."
    )

# --- CONFIGURATIE ---
API_KEY = "JOUW_VISION_BOX_API_KEY"
WS_URL = "wss://backend-url.com/ws/vision"
REST_URL = "http://[IP-VAN-VM2]:8000/api/v1/vision/analyze"

LOCK_PIN = 18
SENSOR_PIN = 23


class VisionBoxClient:
    def __init__(self, loop):
        self.loop = loop
        self.loan_id = None
        self.evaluation_type = None
        self.websocket = None

        if HAS_HARDWARE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(LOCK_PIN, GPIO.OUT)
            GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            # Event listener die reageert op het sluiten van de deur
            GPIO.add_event_detect(
                SENSOR_PIN,
                GPIO.FALLING,
                callback=self.handle_door_closed,
                bouncetime=1000,
            )
        else:
            print("Simulatie: GPIO setup overgeslagen.")

    def open_locker(self):
        """Stuurt het fysieke slot aan of simuleert dit."""
        print(f"Hardware actie: Slot (Pin {LOCK_PIN}) ontgrendelen.")
        if HAS_HARDWARE:
            GPIO.output(LOCK_PIN, GPIO.HIGH)
            time.sleep(2)
            GPIO.output(LOCK_PIN, GPIO.LOW)
        else:
            print("SIMULATIE: Slot is nu 2 seconden OPEN.")

    def handle_door_closed(self, channel):
        """Callback functie getriggerd door de sensor."""
        if self.loan_id and self.evaluation_type:
            print("Systeem: Deur-sluiting gedetecteerd. Start verwerking...")
            # Start de async transactie vanuit een synchrone callback
            asyncio.run_coroutine_threadsafe(self.process_transaction(), self.loop)

    async def process_transaction(self):
        """Beheert de workflow na het sluiten van de deur."""
        # 1. Bevestig sluiting aan backend
        if self.websocket:
            await self.websocket.send(
                json.dumps({"event": "slot_closed", "loan_id": self.loan_id})
            )

        # 2. Beeldregistratie en Validatie
        print("Systeem: Starten camera validatie loop...")
        image_path = self.capture_and_validate()

        if image_path:
            # 3. Upload naar AI Backend
            success = self.send_image_to_backend(image_path)
            if success:
                print("Succes: Afbeelding verzonden en geaccepteerd.")
                self.set_led("green")
            else:
                print("Fout: Backend upload mislukt.")
                self.set_led("orange")
        else:
            print("Fout: Geen valide beeld binnen 5 seconden. Check belichting.")
            self.set_led("orange")

        # Reset status voor de volgende gebruiker
        self.loan_id = None
        self.evaluation_type = None

    def capture_and_validate(self):
        """Probeert een bruikbare foto te maken binnen de tijdslimiet."""
        cap = cv2.VideoCapture(0)
        start_time = time.time()

        while (time.time() - start_time) < 5:
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)

            if brightness > 40:
                path = "valid_capture.jpg"
                cv2.imwrite(path, frame)
                cap.release()
                return path

            time.sleep(0.2)

        cap.release()
        return None

    def send_image_to_backend(self, path):
        """Stuurt de foto via REST naar de AI server."""
        headers = {"X-Device-Token": API_KEY}
        try:
            with open(path, "rb") as f:
                files = {"file": f}
                data = {
                    "loan_id": self.loan_id,
                    "evaluation_type": self.evaluation_type,
                }
                r = requests.post(
                    REST_URL, headers=headers, files=files, data=data, timeout=10
                )
                return r.status_code == 200
        except Exception as e:
            print(f"Netwerkfout: {e}")
            return False

    def set_led(self, color):
        """Update de LED status (indicatie voor gebruiker/admin)."""
        print(f"LED STATUS: {color.upper()}")

    async def listen(self):
        """Hoofdloop voor WebSocket communicatie."""
        headers = {"X-Device-Token": API_KEY}
        try:
            async with websockets.connect(WS_URL, extra_headers=headers) as ws:
                self.websocket = ws
                print(f"Verbonden met backend op {WS_URL}")

                async for message in ws:
                    data = json.loads(message)
                    command = data.get("command")

                    if command == "open_slot":
                        self.loan_id = data.get("loan_id")
                        self.evaluation_type = data.get("evaluation_type")
                        self.open_locker()

                    elif command == "set_led":
                        self.set_led(data.get("color"))
        except Exception as e:
            print(f"Verbindingsfout: {e}")


if __name__ == "__main__":
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    client = VisionBoxClient(event_loop)

    try:
        event_loop.run_until_complete(client.listen())
    except KeyboardInterrupt:
        print("Systeem wordt afgesloten...")
    finally:
        if HAS_HARDWARE:
            GPIO.cleanup()

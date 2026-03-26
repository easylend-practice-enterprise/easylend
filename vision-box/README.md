# Vision Box (Edge Client)

This directory contains the logic for the Vision Box, which runs on a Raspberry Pi 4. It acts as a thin client responsible for controlling physical hardware (electronic locks, LED strips) and capturing images for AI evaluation.

## 1. Overview

The Vision Box bridges the physical lockers with the EasyLend backend. While the heavy AI inference is handled by the server (VM2), the Raspberry Pi performs essential edge computing to ensure data quality and system stability.

## 2. Edge Computing & Image Validation

To prevent the backend from processing useless data (e.g., black or heavily overexposed photos due to lighting issues or camera initialization), the Vision Box enforces local quality checks:

* **Capture Loop:** When a door closes, the camera takes a picture.
* **Local Validation:** A lightweight script checks the frame for basic visibility criteria (e.g., average pixel brightness).
* **Retry Mechanism:** If the image is invalid, the camera retries taking a picture. This loop times out after 5 seconds.
* **Transmission:** Only a single, visually valid frame is sent to the backend.

## 3. Communication Protocol

The Vision Box uses a hybrid communication approach. **Authentication** is strictly enforced via a static API key. You must include the following header in BOTH your WebSocket connection and HTTP POST requests:
`X-Device-Token: <YOUR_VISION_BOX_API_KEY>`

* **WebSockets (WSS):**
  * Listens for `open_slot {locker_id, loan_id, evaluation_type}` commands from the backend. *(Note: Save the `loan_id` and `evaluation_type` in memory; you will need them later).*
  * Listens for `set_led {locker_id, color}` commands to indicate status (green/orange/red).
  * Sends a `slot_closed` event to the backend the moment the physical door shuts.
* **HTTP POST (REST):**
  * Immediately after the `slot_closed` event and edge validation, it sends the image to `POST /api/v1/vision/analyze`.
  * **Payload Format:** Must be sent as `multipart/form-data` containing three required fields:
    1. `file`: The `.jpg` image payload.
    2. `loan_id`: The UUID of the loan (retrieved from the previous WSS command).
    3. `evaluation_type`: Either `"CHECKOUT"` or `"RETURN"` (retrieved from the previous WSS command).

## 4. Fallback & Error Handling

If the edge validation fails completely (e.g., 5-second timeout reached without a valid picture) or the backend API is unreachable:

* The local LED is set to **orange**.
* The transaction cannot be safely completed automatically.
* The backend defaults the loan and asset status to `PENDING_INSPECTION` and the locker to `MAINTENANCE`. A human administrator must manually verify the locker contents via the Quarantine Dashboard.

# WebSocket Protocol (Hardware)

The Vision Box (Raspberry Pi 4) connects to the API via a persistent WebSocket connection to receive real-time commands and report sensor events.

## Connection
**URL**: `ws://<host>/ws/visionbox/{kiosk_id}`
**Auth**: Requires `X-Device-Token` header for authentication.

## Server-to-Client Messages (Commands)

### 1. `open_slot`
Sent when a checkout or return is initiated.
```json
{
  "action": "open_slot",
  "locker_id": 12,
  "loan_id": "<uuid>",
  "evaluation_type": "CHECKOUT"
}
```
- `locker_id`: The physical slot number (logical_number).
- `evaluation_type`: `"CHECKOUT"` or `"RETURN"`.

### 2. `set_led`
Used for status signaling (e.g., green for success, orange for inspection).
```json
{
  "action": "set_led",
  "locker_id": 12,
  "color": "green"
}
```

## Client-to-Server Messages (Events)

### 1. `slot_closed`
Sent by the Vision Box when the physical door sensor detects closure.
```json
{
  "event": "slot_closed",
  "locker_id": "12"
}
```
- *Effect*: Backend logs the event and awaits the subsequent AI analysis photo upload.

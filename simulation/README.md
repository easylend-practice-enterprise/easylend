# Simulation

## What is this?

The simulation is a **digital twin** of the EasyLend Vision Box. It is a lightweight Python script that connects to the backend via WebSocket, acting as a hardware emulator so the API and kiosk app can be fully tested without physical kiosks.

## Scope

- Connect to the API via WebSocket as a Vision Box would (`WSS: /ws/visionbox/{kiosk_id}`)
- Authenticate using a static M2M device token (`X-Device-Token` header)
- Send and receive **WebSocket messages** in the same protocol as the real Vision Box
- Listen for `open_slot` commands and `set_led` commands, and send `slot_closed` events

## Framework

The simulation is a plain Python script using the `websockets` library (no UI framework). It runs headlessly in the terminal and is suitable for CI/CD integration and local development.

```text
simulation/
├── main.py          # Entry point: WebSocket client that connects to the API
├── main.py           # Connects to /ws/visionbox/{kiosk_id}, sends slot_closed, receives open_slot
└── .env.example      # VISIONBOX_WS_URL, SIMULATION_API_KEY
```

## Connection to the API

```text
WS:  ws://<api-host>:/ws/visionbox/{kiosk_id}
WSS: wss://<api-host>:/ws/visionbox/{kiosk_id}
Headers: X-Device-Token: <SIMULATION_API_KEY>
```

The simulation behaves like a Vision Box: it receives `open_slot` and `set_led` commands and sends `slot_closed` events back.

## Setup

1. Copy `.env.example` to `.env` and set your API URL and simulation key:
   ```bash
   cp .env.example .env
   ```

2. Install dependencies:
   ```bash
   cd simulation
   uv sync
   ```

3. Run the simulation:
   ```bash
   uv run python main.py
   ```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VISIONBOX_WS_URL` | `ws://localhost:8000/ws/visionbox/00000000-0000-0000-0000-000000000000` | WebSocket URL of the API |
| `SIMULATION_API_KEY` | `local-dev-sim-key-123` | Static device token (must match backend `SIMULATION_API_KEY`) |

# Simulation

## What is this?

The simulation is a **digital twin** of the EasyLend locker kiosk. It is a Python application with a web UI that virtually mimics a grid of physical lockers.

Instead of real hardware, the simulation communicates directly with the API via WebSockets (acting as a regular Vision Box), allowing the backend to be fully tested without physical kiosks.

## Scope

- Visualise a **locker grid** with real-time statuses (`AVAILABLE`, `OCCUPIED`, `MAINTENANCE`, `ERROR_OPEN`)
- Simulate hardware events: slot opening/closing, LED colour change
- Send and receive **WebSocket messages** (same protocol as the real Vision Box)
- Authentication via a **static M2M API key** (`X-Device-Token` header)

## Connection to the API

```text
WSS: wss://<api-host>/ws/visionbox
Headers: X-Device-Token: <static_key>
```

The simulation behaves like a Vision Box: it listens for `open_slot` events and sends `slot_closed` events back.

## Framework

Not yet decided. Candidates:

| Framework | Pro | Con |
| --- | --- | --- |
| **Streamlit** | Fast, Python-native, easy grid UI | Less control over WebSocket lifecycle |
| **FastAPI + HTMX** | Consistent with the rest of the stack (FastAPI already used in backend) | More boilerplate |
| **Flask + Socket.IO** | Simple, good WebSocket support | Extra dependency |

> Selection will be made at the start of ELP-32 (Choose simulation framework).

## Directory Structure (planned)

```text
simulation/
├── README.md         # This file
├── main.py           # Entry point
├── config.py         # API URL, API key via .env
├── websocket.py      # WSS client logic
├── ui/               # Web UI components
└── .env.example      # API_URL, DEVICE_TOKEN
```

## Setup (not yet available)

See ELP-32 to ELP-35 for the final setup instructions once the framework is chosen.

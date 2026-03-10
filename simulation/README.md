# Simulatie

## Wat is dit?

De simulatie is een **digital twin** van de EasyLend locker-kiosk. Het is een Python-applicatie met een web UI die een grid van fysieke lockers virtueel nabootst.

In plaats van echte hardware spreekt de simulatie rechtstreeks met de API via WebSockets (als een gewone Vision Box), zodat de backend volledig getest kan worden zonder fysieke kiosks.

## Scope

- Visualiseer een **lockersgrid** met real-time statussen (`AVAILABLE`, `OCCUPIED`, `MAINTENANCE`, `ERROR_OPEN`)
- Simuleer hardware-events: slot openen/sluiten, LED-kleurverandering
- Stuur en ontvang **WebSocket-berichten** (zelfde protocol als de echte Vision Box)
- Authenticatie via **statische M2M API-key** (`X-Device-Token` header)

## Verbinding met de API

```text
WSS: wss://<api-host>/ws/device
Headers: X-Device-Token: <static_key>
```

De simulatie gedraagt zich als een Vision Box: ze luistert naar `open_slot` / `close_slot` events en stuurt `slot_closed` events terug.

## Framework

Nog niet vastgelegd. Kandidaten:

| Framework | Pro | Con |
| --- | --- | --- |
| **Streamlit** | Snel, Python-native, makkelijk grid UI | Minder controle over WebSocket lifecycle |
| **FastAPI + HTMX** | Consistent met rest van de stack (al FastAPI in backend) | Meer boilerplate |
| **Flask + Socket.IO** | Eenvoudig, goede WebSocket ondersteuning | Extra dependency |

> Keuze wordt gemaakt bij start van ELP-32 (Simulatie framework kiezen).

## Mapstructuur (gepland)

```text
simulation/
├── README.md         # Dit bestand
├── main.py           # Startpunt
├── config.py         # API URL, API key via .env
├── websocket.py      # WSS client logic
├── ui/               # Web UI componenten
└── .env.example      # API_URL, DEVICE_TOKEN
```

## Setup (nog niet beschikbaar)

Zie ELP-32 tot ELP-35 voor de uiteindelijke setup-instructies zodra het framework gekozen is.

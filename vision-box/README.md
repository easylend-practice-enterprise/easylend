# 🛠️ EasyLend: Vision Box (Operational Guide)

> **Note:** For high-level architecture, business logic, and system-wide design decisions, please refer to the **[Global Documentation Index](../docs/INDEX.md)**.

This directory contains the edge client logic for the Raspberry Pi 4 "Vision Box."

## Hardware Requirements
- Raspberry Pi 4 (8GB recommended)
- Electronic Lock (connected via GPIO)
- LED Strip
- Pi Camera or USB Camera

## Setup & Execution

```bash
# Sync dependencies
uv sync

# Run the edge client
uv run python main.py
```

## Environment Variables
Ensure the following are set in your `.env` file:
- `VISIONBOX_WS_URL`: WebSocket endpoint of the API.
- `VISION_BOX_API_KEY`: Secret token matching the backend configuration.

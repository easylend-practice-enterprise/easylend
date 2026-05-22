# 🛠️ EasyLend: Simulator (Operational Guide)

> **Note:** For high-level architecture, business logic, and system-wide design decisions, please refer to the **[Global Documentation Index](../docs/INDEX.md)**.

The simulation is a **digital twin** of the EasyLend Vision Box. It acts as a hardware emulator for development and testing.

## Running the Simulation

```bash
# Sync dependencies
uv sync

# Run the simulator
uv run python main.py
```

## Configuration

Requires a `.env` file with:

- `VISIONBOX_WS_URL`: The WebSocket URL for the kiosk being simulated.
- `SIMULATION_API_KEY`: Matching the backend simulator key.

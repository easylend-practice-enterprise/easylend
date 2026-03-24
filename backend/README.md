# EasyLend Backend Infrastructure

This directory contains the backend infrastructure for the EasyLend platform. We use a microservices-inspired architecture split across different Virtual Machines.

## Orchestration Guide (Docker Compose)

Because our services run on different Proxmox VMs, we use separate Docker Compose environments:

### 1. Root Orchestration (Main Backend)

**Files:** `docker-compose.local.yml` / `docker-compose.prod.yml`
**Location:** `/backend/`
**Runs on:** Main VM
**Purpose:** Manages the core infrastructure:

- FastAPI (Main API)
- PostgreSQL Database
- Redis Cache
- pgAdmin (Local only)
- Watchtower (Prod only)

### 2. Vision AI Orchestration (Microservice)

**Files:** `docker-compose.local.yml` / `docker-compose.prod.yml`
**Location:** `/backend/vision/`
**Runs on:** VM2 (Intel Xeon Optimized)
**Purpose:** Runs the isolated YOLO/OpenVINO AI inference engine. Separated because it requires specific CPU resources and runs on a dedicated edge/AI node.

## Quick Start

### Prerequisites

- Docker + Docker Compose installed
- Correct `.env` values for each environment (at minimum secrets and API keys)

### Start Local Main Backend Stack (from `/backend`)

```bash
docker compose -f docker-compose.local.yml up -d --build
```

### Start Local Vision Stack (from `/backend/vision`)

```bash
docker compose -f docker-compose.local.yml up -d --build
```

### Start Production Main Backend Stack (from `/backend`)

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Start Production Vision Stack (from `/backend/vision`)

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Stop Stacks

```bash
docker compose -f docker-compose.local.yml down
docker compose -f docker-compose.prod.yml down
```

### Useful Notes

- Main backend and Vision are intentionally orchestrated separately because they run on different VMs.
- Watchtower should only run in production compose files, not in local development compose files.
- Model artifacts (`*.pt`) are intentionally excluded from git and image context; provide them via runtime mount or model update flow.

## Health Checks (Quick)

```bash
# Main API (from VM1)
curl http://localhost:8000/health

# Vision API (from VM2, local compose default port)
curl http://localhost:8001/health
```

## Environment Variables (Minimum)

- Main backend: DB connection vars, Redis vars, JWT secret.
- Vision: `VISION_API_KEY` (required), `MODEL_PATH` (prod), `SKIP_MODEL_LOADING=1` (local dev optional).

## Troubleshooting (Short)

- Port already in use: stop old containers or change compose port mapping.
- `unhealthy` service: check logs with `docker compose logs -f <service>`.
- Vision model not loaded: verify model mount/path or run model update flow.
- DB migration issues: run from `backend/api` and confirm database container is up.

## Database Migrations (Alembic)

We use **Alembic** to safely apply changes to our SQLAlchemy models (`models.py`) to the PostgreSQL database. This ensures that our database structure is always in sync with our code.

### The 3 Key Commands

Make sure your terminal is in the `backend/api` directory and your Docker database is running before using these commands.

**1. Stage a new change (Autogenerate)**
Have you added a new table, column, or relationship in `models.py`? Let Alembic detect the differences and generate a migration script:

```bash
uv run alembic revision --autogenerate -m "Short description of your change"

```

*(Always inspect the generated file in `alembic/versions/` to verify that Alembic interpreted everything correctly!)*

**2. Apply the change to the database (Upgrade)**
Once your script is ready (or after pulling a colleague's code), run this command to actually update the database:

```bash
uv run alembic upgrade head

```

**3. Undo a mistake (Downgrade)**
Have you accidentally applied a bad migration to your local database? You can roll back one step with:

```bash
uv run alembic downgrade -1

```

*(Note: In PostgreSQL, `Enum` types are sometimes not automatically removed during a downgrade. When setting up a completely fresh local environment, it can be faster to reset your Docker container with `docker compose down -v`).*

## Hardware Integration Security & Stability

The backend interacts with the physical Vision Box (Raspberry Pi) via WebSockets and HTTP POST. To ensure system stability and security (Zero Trust Architecture), the following patterns are enforced:

### 1. Strict M2M Validation

Even though the Vision Box communicates over a secure VPN, the `/api/v1/vision/analyze` endpoint strictly validates incoming files:

- **MIME Type Check:** Rejects non-image payloads immediately.
- **Memory Limits:** Enforces a hard 10MB limit during the read phase to prevent Out-Of-Memory (OOM) crashes caused by malfunctioning edge cameras.

### 2. Async & Deferred File Storage

Images are stored on a local Docker volume (`/app/uploads`) to be served later for audit purposes.

- **Non-Blocking I/O:** Disk writes are performed asynchronously using `aiofiles` to keep the FastAPI event loop unblocked.
- **Deferred Write:** Files are only written to disk *after* a successful response from the VM2 AI service. This prevents the accumulation of orphaned files if the AI service is down or rejects the image.

### 3. WebSocket Connection Resilience

Network drops between the server and the hardware are expected.

- **Safe Transmission:** All `manager.send_command()` calls in `websockets.py` are wrapped in a `try...except` block. If the socket is dead, the exception is caught, the kiosk is safely removed from `active_connections`, and the server continues running without crashing the current transaction thread.

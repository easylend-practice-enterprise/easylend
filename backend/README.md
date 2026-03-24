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

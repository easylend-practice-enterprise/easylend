# 🛠️ EasyLend: Core API (Operational Guide)

> **Note:** For high-level architecture, business logic, and system-wide design decisions, please refer to the **[Global Documentation Index](../../docs/INDEX.md)**.

This directory contains the FastAPI-based core backend for EasyLend.

## Development Setup

We use [uv](https://docs.astral.sh/uv/) for Python package management.

```bash
# Sync dependencies and create venv
uv sync

# Run the API server with hot-reload
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir .
```

## Database Management

Migrations are handled via Alembic.

```bash
# Apply migrations to head
uv run alembic upgrade head

# Generate a new migration
uv run alembic revision --autogenerate -m "description"
```

## Testing & Quality

```bash
# Run integration tests (requires Docker)
uv run pytest app/tests/integration/

# Run unit tests
uv run pytest app/tests/

# Lint and Format
uv run ruff check . --fix
uv run ruff format .
```

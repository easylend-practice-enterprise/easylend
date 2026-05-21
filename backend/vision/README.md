# 🛠️ EasyLend: Vision AI Service (Operational Guide)

> **Note:** For high-level architecture, business logic, and system-wide design decisions, please refer to the **[Global Documentation Index](../../docs/INDEX.md)**.

This directory contains the YOLO-based Vision AI microservice.

## Prerequisites
- **Hardware**: Optimized for Intel Xeon/Core CPUs with OpenVINO.
- **Python**: 3.13+

## Development Setup

```bash
# Sync dependencies
uv sync

# Run the Vision service
uv run uvicorn main:app --host 0.0.0.0 --port 8001
```

## Testing

Tests skip heavy model loading for speed.
```bash
# Run tests
uv run pytest

# Linting
uv run ruff check . --fix
```

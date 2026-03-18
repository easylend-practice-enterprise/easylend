# EasyLend

Monorepo for the EasyLend Practice Enterprise project.
This repository contains the full stack for the EasyLend kiosk, including the backend, frontend, computer vision, and infrastructure.

## Documentation

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/easylend-practice-enterprise/easylend)

[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/easylend-practice-enterprise/easylend)

View our documentation for a detailed overview of the system:

- [Architecture](docs/architecture.md) - *Proxmox, Networking, AI Microservice & Database ERD.*
- [Workflows](docs/workflows.md) - *Sequence diagrams for checkout, return, AI quarantine, and PXE boot checks.*
- [Git Guidelines](CONTRIBUTING.md) - *Our conventions for YouTrack, branches, and cross-platform (Windows/Linux) development.*

## Project Structure

- `.github/`: GitHub Actions and CI/CD workflows (work in progress).
- `backend/`:
  - `api/`: The REST API backend (FastAPI).
  - `database/`: Docker Compose configurations for the infrastructure (PostgreSQL, Redis, pgAdmin, SQLBak).
- `docs/`: Architecture documentation and diagrams (Mermaid/SVG).
- `kiosk-app/`: The Android/Frontend kiosk application (Flutter).
- `simulation/`: Scripts for simulating hardware interactions and workflows.
- `vision-box/`: Computer vision components for object recognition in the Vision Box.

## Setup

See the respective folders for domain-specific setup instructions. The main infrastructure (database, cache, monitoring) is managed via Docker Compose in `backend/database`.

## Pre-commit

Pre-commit is configured via `.pre-commit-config.yaml` in the root and applies to all Python microservices (`backend/api`, `backend/vision`, `simulation`). **Not** applicable to the Flutter kiosk app.

Hooks that run on every commit:

| Hook | Description |
| --- | --- |
| `ruff-check` | Linter (incl. security, isort, pyupgrade) with auto-fix enabled |
| `ruff-format` | Code formatter |

One-time installation in the repo root:

```bash
# Make sure you are in the ROOT of the repository
uv tool install pre-commit
pre-commit install
```

Manually check all files:

```bash
# Manually check everything
pre-commit run --all-files
```

## Team

Maxim Huardel, Jasper Savels, and Injo De Pot are the primary developers of this project. We collaborate closely and follow the guidelines in `CONTRIBUTING.md` for a streamlined workflow.

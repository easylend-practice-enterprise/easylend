# EasyLend

Monorepo voor het EasyLend Practice Enterprise project.
Dit repository bevat de volledige stack voor de EasyLend kiosk, inclusief backend, frontend, computer vision en infrastructuur.

## Project Structuur

- `.github/`: GitHub Actions en CI/CD workflows (work in progress).
- `backend/`:
  - `api/`: De REST API backend (FastAPI).
  - `database/`: Docker Compose configuraties voor de infrastructuur (PostgreSQL, Redis, pgAdmin, SQLBak).
- `docs/`: Architectuur documentatie en diagrammen (Mermaid/SVG).
- `kiosk-app/`: De Android/Frontend kiosk applicatie (Kotlin).
- `simulation/`: Scripts voor het simuleren van hardware-interacties en workflows.
- `vision-box/`: Computer vision componenten voor objectherkenning in de Vision Box.

## Setup

Zie de respectievelijke mappen voor specifieke setup-instructies per domein. De hoofd-infrastructuur (database, cache, monitoring) wordt beheerd via Docker Compose in `backend/database`.

## Team

Maxim, Jasper en Injo

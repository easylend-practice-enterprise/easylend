# EasyLend

Monorepo voor het EasyLend Practice Enterprise project.
Dit repository bevat de volledige stack voor de EasyLend kiosk, inclusief backend, frontend, computer vision en infrastructuur.

## Documentatie

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/easylend-practice-enterprise/easylend)

Bekijk onze documentatie voor meer duidelijkheid over het systeem:

- [Architectuur](docs/architecture.md) - *Proxmox, Netwerken, AI Microservice & Database ERD.*
- [Workflows](docs/workflows.md) - *Sequence diagrammen van de checkout, inlevering, AI quarantaine en PXE boot checks.*
- [Git Regels](CONTRIBUTING.md) - *Onze afspraken over YouTrack, branches en cross-platform (Windows/Linux) ontwikkeling.*

## Project Structuur

- `.github/`: GitHub Actions en CI/CD workflows (work in progress).
- `backend/`:
  - `api/`: De REST API backend (FastAPI).
  - `database/`: Docker Compose configuraties voor de infrastructuur (PostgreSQL, Redis, pgAdmin, SQLBak).
- `docs/`: Architectuur documentatie en diagrammen (Mermaid/SVG).
- `kiosk-app/`: De Android/Frontend kiosk applicatie (Flutter).
- `simulation/`: Scripts voor het simuleren van hardware-interacties en workflows.
- `vision-box/`: Computer vision componenten voor objectherkenning in de Vision Box.

## Setup

Zie de respectievelijke mappen voor specifieke setup-instructies per domein. De hoofd-infrastructuur (database, cache, monitoring) wordt beheerd via Docker Compose in `backend/database`.

## Team

Maxim Huardel, Jasper Savels en Injo De Pot zijn de hoofdontwikkelaars van dit project. We werken nauw samen en volgen de richtlijnen in `CONTRIBUTING.md` voor een gestroomlijnde samenwerking.

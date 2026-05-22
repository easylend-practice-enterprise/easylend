# EasyLend

EasyLend is an IoT-enabled equipment lending platform designed for educational campuses. It automates the lending and return process of assets (like laptops and tablets) using a combination of Flutter kiosk applications, Raspberry Pi-powered Vision Boxes, and server-side AI for automated damage inspection.

---

## 📚 Technical Documentation

For detailed insights into our system architecture, API specifications, and hardware integration, please refer to our **[Central Documentation Index](./docs/INDEX.md)**.

### Quick Links

- **[System Topology](./docs/architecture/01_topology.md)**
- **[API Principles & IoT Patterns](./docs/api/01_rest_principles.md)**
- **[Lending State Machine](./docs/architecture/02_state_machine.md)**
- **[Vision AI Integration](./docs/hardware/01_vision_integration.md)**

---

## 🚀 Running the Project

### Prerequisites

- Docker & Docker Compose
- Python 3.13+ (for local development)
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Backend Setup (API & AI)

1. Navigate to `backend/api` and run `uv sync`.
2. Navigate to `backend/vision` and run `uv sync`.
3. Start the infrastructure using Docker:

   ```bash
   cd backend
   docker-compose -f docker-compose.local.yml up -d
   ```

### Running Tests

We use a Testcontainers-based integration suite for the API:

```bash
cd backend/api
uv run pytest app/tests/integration/
```

---

## 👥 The Team

**Maxim Huardel, Jasper Savels, and Injo De Pot**
*EA ICT: Final Year Practice Enterprise Project*

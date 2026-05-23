# 🛠️ EasyLend: Backend Infrastructure (Operational Guide)

> **Note:** For high-level architecture, business logic, and system-wide design decisions, please refer to the **[Global Documentation Index](../docs/INDEX.md)**.

This directory contains the Docker Compose infrastructure to orchestrate the EasyLend backend components.

## Running the Stack

You can run the entire backend stack (API, Timeout Worker, Overdue Worker, Database, Redis) using Docker Compose.

### Local Development

Runs the stack with local ports exposed and mounts source code for hot-reloading:

```bash
docker-compose -f docker-compose.local.yml up -d --build
```

### Production

Runs the stack in a secure, isolated network without exposing database ports:

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

## Useful Commands

- **View Logs:** `docker-compose -f docker-compose.local.yml logs -f`
- **Tear Down:** `docker-compose -f docker-compose.local.yml down -v`
- **Rebuild specific service:** `docker-compose -f docker-compose.local.yml up -d --build api`

## Full Reset & Seeding (Development)

If you want to start from a completely clean state (purge all data) and populate the database with real-world scenarios for testing:

1. **Prepare Environment:**

    ```powershell
    # From project root
    .\Setup-Envs.ps1 -Force
    ```

2. **Purge & Rebuild (No Cache):**

    ```bash
    # From project root
    docker compose -f docker-compose.local.yml down -v
    docker compose -f vision/docker-compose.local.yml down -v

    docker compose -f docker-compose.local.yml build --no-cache
    docker compose -f vision/docker-compose.local.yml build --no-cache
    ```

3. **Start Stack:**

    ```bash
    docker compose -f docker-compose.local.yml up -d
    docker compose -f vision/docker-compose.local.yml up -d
    ```

4. **Run Dev Seeder:**

    ```powershell
    cd api
    # Use --reset to wipe the database before seeding (recommended for dev)
    uv run scripts/seed_dev.py --reset
    ```

## Production Bootstrapping

When deploying to a new location or a clean production environment where you do NOT want test data:

1. **Start Minimal Stack:**

    ```bash
    # Ensure Docker Compose is up for the target environment
    docker compose -f docker-compose.prod.yml up -d
    ```

2. **Bootstrap Roles & Admin:**

    ```powershell
    cd api
    uv run scripts/bootstrap.py
    ```

    *Optional: Use `uv run scripts/bootstrap.py --force-purge` if you need to wipe an existing non-production environment completely before bootstrapping.*

After running `bootstrap.py`, the system is in a "sterile" but secure state. You can now log in via the **Digital Twin / Management Interface** to configure real kiosks, lockers, and assets.

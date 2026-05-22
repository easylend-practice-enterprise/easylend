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

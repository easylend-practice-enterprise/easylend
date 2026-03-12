FROM python:3.12-slim

WORKDIR /app

# Optimalisaties voor uv en Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV PYTHONUNBUFFERED=1

# Kopieer de razendsnelle 'uv' binary rechtstreeks van de makers
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# STAP 1: Kopieer ALLEEN de lockfiles en installeer dependencies.
# Dit is een gigantische snelheids-boost, want deze Docker-laag wordt nu 
# gecachet zolang je geen nieuwe packages toevoegt aan pyproject.toml!
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# STAP 2: Kopieer de rest van de applicatie
COPY app/ ./app/
COPY alembic.ini .
COPY alembic/ ./alembic/

# STAP 3: Sync het project zelf (razendsnel want dependencies zijn er al)
RUN uv sync --locked

# Activeer de virtuele omgeving automatisch voor alle volgende commando's
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# EERST migraties runnen, DAN uvicorn starten bij successvolle migraties
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
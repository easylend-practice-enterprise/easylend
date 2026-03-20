FROM python:3.12-slim

WORKDIR /app

# Installeer systeem-afhankelijkheden voor OpenCV (Cruciaal voor YOLO)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Optimalisaties voor uv en Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV PYTHONUNBUFFERED=1

# Kopieer de razendsnelle 'uv' binary rechtstreeks van de makers
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# STAP 1: Kopieer ALLEEN de lockfiles en installeer dependencies.
# Dit zorgt voor extreem snelle Docker caching!
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# STAP 2: Kopieer de rest van de applicatie
RUN mkdir -p models
COPY . .

# STAP 3: Sync het project zelf
RUN uv sync --locked

# Activeer de virtuele omgeving automatisch voor alle volgende commando's
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Start de applicatie (geen Alembic nodig hier, het is pure AI)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
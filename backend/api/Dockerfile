FROM python:3.13-slim

WORKDIR /app

# Force upgrade minimal OpenSSL runtime packages to patch CVE-2026-2673 via Debian security repo
RUN echo "deb http://deb.debian.org/debian-security trixie-security main" > /etc/apt/sources.list.d/trixie-security.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade openssl libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Optimizations for uv and Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV PYTHONUNBUFFERED=1

# Copy the fast 'uv' binary directly from the image publisher
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# STEP 1: Copy ONLY the lockfiles and install dependencies.
# This provides a major speed boost because this Docker layer stays cached
# until you add new packages to pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# STEP 2: Copy the rest of the application
COPY app/ ./app/
COPY alembic.ini .
COPY alembic/ ./alembic/

# STEP 3: Sync the project itself (fast because dependencies are already present)
RUN uv sync --locked

# Activate the virtual environment automatically for all subsequent commands
ENV PATH="/app/.venv/bin:$PATH"

# Create a non-root user with a writable home directory
RUN addgroup --system appgroup && adduser --system --home /home/appuser --ingroup appgroup appuser
RUN mkdir -p /home/appuser
RUN chown -R appuser:appgroup /app /home/appuser

# Set HOME for libraries/tools that rely on user-scoped cache/config paths
ENV HOME=/home/appuser

# Switch to the non-root user
USER appuser

EXPOSE 8000

# Run migrations first, then start uvicorn when migrations succeed
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
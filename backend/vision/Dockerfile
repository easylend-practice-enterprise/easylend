FROM python:3.13-slim

WORKDIR /app

# Install dependencies for OpenCV and force upgrade OpenSSL via Debian security repo to patch CVE-2026-2673
RUN echo "deb http://deb.debian.org/debian-security trixie-security main" > /etc/apt/sources.list.d/trixie-security.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && apt-get install -y --no-install-recommends --only-upgrade openssl libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Optimizations for uv and Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV PYTHONUNBUFFERED=1

# Copy the blazingly fast 'uv' binary directly from the image publisher
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# STEP 1: Copy ONLY the lockfiles and install dependencies.
# This provides a major speed boost because this Docker layer stays cached
# until you add new packages to pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# STEP 2: Copy the rest of the application
RUN mkdir -p models
COPY . .

# STEP 3: Sync the project itself
RUN uv sync --locked

# Activate the virtual environment automatically for all subsequent commands
ENV PATH="/app/.venv/bin:$PATH"

# Create a non-root user with a writable home directory for runtime caches
RUN addgroup --system appgroup && adduser --system --home /home/appuser --ingroup appgroup appuser
RUN mkdir -p /home/appuser
RUN chown -R appuser:appgroup /app /home/appuser

# Set HOME for libraries that write under ~/.cache or ~/.config
ENV HOME=/home/appuser

# Switch to the non-root user
USER appuser

EXPOSE 8000

# Start the application with uvicorn
# optional: uv run gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
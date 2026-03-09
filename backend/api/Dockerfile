FROM python:3.12-slim

WORKDIR /app

# uv dependencies
COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv

# geen venv nodig in container
RUN uv pip install --system -r pyproject.toml

# api code
COPY app/ ./app/

# alembic migraties
COPY alembic.ini .
COPY alembic/ ./alembic/

# poort voor FastAPI
EXPOSE 8000

# EERST migraties runnen, DAN uvicorn starten bij successvolle migraties
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
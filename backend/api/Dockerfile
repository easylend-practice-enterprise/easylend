# Gebruik een officiële, lichtgewicht Python image
FROM python:3.12-slim

# Zet de werkmap in de container
WORKDIR /app

# Kopieer de uv dependency files
COPY pyproject.toml uv.lock ./

# Installeer uv in de container
RUN pip install --no-cache-dir uv

# Gebruik uv om de dependencies te installeren (system-wide in de container, geen venv nodig)
RUN uv pip install --system -r pyproject.toml

# Kopieer de rest van de backend code
COPY app/ ./app/

# Exposeer de poort voor FastAPI
EXPOSE 8000

# Start de applicatie
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir ".[api]"

# Copy seed data (read-only registry, ~140KB)
COPY data/ data/

# Frontend pre-built by GitHub Actions
COPY web/dist/ static/

EXPOSE 8080

CMD ["uvicorn", "pnw_campsites.api:app", "--host", "0.0.0.0", "--port", "8080"]

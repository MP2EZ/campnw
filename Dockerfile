FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir ".[api]"

# Copy seed data to staging dir (volume will mount over /app/data/)
COPY data/ data-seed/

# Frontend pre-built by GitHub Actions
COPY web/dist/ static/

# Copy design tokens into SEO static dir for server-rendered pages
COPY web/src/tokens.css src/pnw_campsites/seo-static/tokens.css

# Operations scripts (compaction, etc.)
COPY scripts/ scripts/

# Startup script: copy seed data into volume if missing, then run server
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]

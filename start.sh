#!/bin/sh
# Ensure /app/data/ exists (volume mount point)
mkdir -p /app/data

# Copy seed registry into volume only if not present.
if [ ! -f /app/data/registry.db ]; then
  cp /app/data-seed/registry.db /app/data/registry.db
fi

exec uvicorn pnw_campsites.api:app --host 0.0.0.0 --port 8080

#!/bin/sh
# Ensure /app/data/ exists (volume mount point)
mkdir -p /app/data

# Copy seed registry into volume if not present (or update on new deploys)
# Registry is read-only reference data — always safe to overwrite
cp /app/data-seed/registry.db /app/data/registry.db

exec uvicorn pnw_campsites.api:app --host 0.0.0.0 --port 8080

#!/bin/bash
# Sync local registry.db to Fly.io persistent volume.
# Run after enrichment, re-seeding, or any local DB changes.
#
# Usage:
#   ./scripts/sync-registry.sh
#   ./scripts/sync-registry.sh --no-restart

set -euo pipefail

APP="campnw"
LOCAL_DB="data/registry.db"
REMOTE_DB="/app/data/registry.db"

if [ ! -f "$LOCAL_DB" ]; then
  echo "Error: $LOCAL_DB not found"
  exit 1
fi

SIZE=$(du -h "$LOCAL_DB" | cut -f1)
echo "Uploading $LOCAL_DB ($SIZE) to $APP:$REMOTE_DB..."

# Upload via sftp
echo "put $LOCAL_DB $REMOTE_DB" | fly sftp shell -a "$APP"

echo "Upload complete."

# Restart unless --no-restart flag
if [ "${1:-}" != "--no-restart" ]; then
  echo "Restarting app to pick up changes..."
  fly machines restart -a "$APP"
  echo "Done."
else
  echo "Skipped restart (--no-restart). Changes will apply on next deploy or restart."
fi

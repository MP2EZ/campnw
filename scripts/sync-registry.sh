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
MACHINE_ID="819525a9961e48"

# Cross-platform file size (macOS BSD / Linux GNU).
file_size() {
  stat -f%z "$1" 2>/dev/null || stat -c%s "$1"
}

if [ ! -f "$LOCAL_DB" ]; then
  echo "Error: $LOCAL_DB not found"
  exit 1
fi

LOCAL_SIZE=$(file_size "$LOCAL_DB")
SIZE_HUMAN=$(du -h "$LOCAL_DB" | cut -f1)
echo "Uploading $LOCAL_DB ($SIZE_HUMAN, $LOCAL_SIZE bytes) to $APP:$REMOTE_DB..."

# Pre-flight: verify ssh works before we rm the remote file.
# Fly's wireguard gateway in sjc1 has been known to TLS-handshake-fail
# intermittently — better to abort with a clear message than rm the
# remote DB and then fail on the sftp put.
if ! fly ssh console -a "$APP" -C "echo ok" >/dev/null 2>&1; then
  echo "ERROR: fly ssh console is not working. Aborting before touching the remote file."
  echo "  Common fix: pkill -f 'fly agent' && retry."
  exit 1
fi

# Remove existing remote file — sftp put won't overwrite.
fly ssh console -a "$APP" -C "rm -f $REMOTE_DB"

# Upload via sftp.
echo "put $LOCAL_DB $REMOTE_DB" | fly sftp shell -a "$APP"

# Verify remote size matches local. Guards against the silent-truncation
# failure mode (sftp shell prints "Upload complete" but the remote was
# 1.1MB short, leaving SQLite seeing a malformed disk image).
REMOTE_SIZE=$(fly ssh console -a "$APP" -C "stat -c%s $REMOTE_DB" 2>/dev/null \
  | tr -d '\r' \
  | grep -E '^[0-9]+$' \
  | tail -1)

if [ -z "${REMOTE_SIZE:-}" ]; then
  echo "ERROR: could not stat remote file after upload. Aborting before restart."
  echo "       Remote DB may be missing or corrupt — re-run this script."
  exit 1
fi

if [ "$LOCAL_SIZE" != "$REMOTE_SIZE" ]; then
  echo "ERROR: upload size mismatch."
  echo "       Local:  $LOCAL_SIZE bytes"
  echo "       Remote: $REMOTE_SIZE bytes"
  echo "       The upload was truncated. Do NOT restart — the remote DB is corrupt."
  echo "       Re-run this script to retry."
  exit 1
fi

echo "Upload verified: $LOCAL_SIZE bytes match remote."

# Restart unless --no-restart flag.
if [ "${1:-}" != "--no-restart" ]; then
  echo "Restarting machine $MACHINE_ID to pick up changes..."
  fly machine restart "$MACHINE_ID" -a "$APP"
  echo "Done."
else
  echo "Skipped restart (--no-restart). Changes will apply on next deploy or restart."
fi

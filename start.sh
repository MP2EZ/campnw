#!/bin/sh
# Ensure /app/data/ exists (volume mount point)
mkdir -p /app/data

# Copy seed registry into volume only if not present.
if [ ! -f /app/data/registry.db ]; then
  cp /app/data-seed/registry.db /app/data/registry.db
fi

# Backfill drive_times from seed DB if the volume DB has none.
# This ensures pre-computed Mapbox drive times survive deploys without
# manual sync-registry.sh runs.
python3 -c "
import sqlite3
vol = sqlite3.connect('/app/data/registry.db')
vol.execute('CREATE TABLE IF NOT EXISTS drive_times (base_name TEXT NOT NULL, booking_system TEXT NOT NULL, facility_id TEXT NOT NULL, drive_minutes INTEGER NOT NULL, drive_miles REAL, source TEXT NOT NULL DEFAULT \"mapbox\", computed_at TEXT NOT NULL, PRIMARY KEY (base_name, booking_system, facility_id))')
count = vol.execute('SELECT COUNT(*) FROM drive_times').fetchone()[0]
if count == 0:
    try:
        seed = sqlite3.connect('/app/data-seed/registry.db')
        rows = seed.execute('SELECT * FROM drive_times').fetchall()
        if rows:
            vol.executemany('INSERT OR REPLACE INTO drive_times VALUES (?,?,?,?,?,?,?)', rows)
            vol.commit()
            print(f'Backfilled {len(rows)} drive_times from seed DB')
        seed.close()
    except Exception as e:
        print(f'Drive times backfill skipped: {e}')
else:
    print(f'Drive times OK: {count} rows')
vol.close()
" 2>&1

exec uvicorn pnw_campsites.api:app --host 0.0.0.0 --port 8080

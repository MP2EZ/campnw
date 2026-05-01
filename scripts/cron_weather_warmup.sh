#!/bin/bash
# Hourly weather cache warmup — tests quota with 1 call, then runs full batch.
# Logs to /tmp/weather-warmup.log

cd /Users/max/dev/pnw-campsite-tool

# Load env vars (cron runs in a bare environment)
set -a
source .env 2>/dev/null
set +a

echo "--- $(date) ---" >> /tmp/weather-warmup.log

# Test with 1 call to see if quota is available
OUTPUT=$(.venv/bin/python3 scripts/warm_weather_cache.py --limit 1 2>&1)

if echo "$OUTPUT" | grep -q "Rate limited\|0 to fetch\|Nothing to do"; then
    echo "Skipped: quota exhausted or nothing to do" >> /tmp/weather-warmup.log
    exit 0
fi

if echo "$OUTPUT" | grep -q "months cached"; then
    echo "Quota available — running full batch" >> /tmp/weather-warmup.log
    .venv/bin/python3 scripts/warm_weather_cache.py --limit 140 >> /tmp/weather-warmup.log 2>&1
else
    echo "Test call failed: $OUTPUT" >> /tmp/weather-warmup.log
fi

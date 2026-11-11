"""Blocking provider calls must not starve asyncio's default executor.

Prod runs on one CPU, so the default executor has min(32, 1 + 4) = 5 workers.
DNS lookups (loop.getaddrinfo, used by httpx for Recreation.gov and the PostHog
proxy) and every asyncio.to_thread caller share that pool. When curl_cffi
provider calls ran there, a handful of slow Oregon parks held every worker and
DNS queued behind them (the 2026-11-07 Oregon stall).
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

import pytest

from pnw_campsites.providers.goingtocamp import GoingToCampClient
from pnw_campsites.providers.reserveamerica import ReserveAmericaClient

# Prod's default executor: min(32, os.cpu_count() + 4) with cpu_count() == 1.
PROD_DEFAULT_WORKERS = 5
PROVIDER_CALL_S = 0.5


@pytest.fixture
async def one_cpu_default_executor():
    loop = asyncio.get_running_loop()
    pool = ThreadPoolExecutor(max_workers=PROD_DEFAULT_WORKERS)
    loop.set_default_executor(pool)
    yield
    pool.shutdown(wait=True)


async def _dns_style_latency() -> float:
    """Time a to_thread call, the way loop.getaddrinfo uses the default pool."""
    t0 = time.monotonic()
    await asyncio.to_thread(lambda: None)
    return time.monotonic() - t0


def _slow_fetch(*_args, **_kwargs):
    time.sleep(PROVIDER_CALL_S)
    return [], 0


async def test_reserveamerica_calls_leave_default_executor_free(
    one_cpu_default_executor,
) -> None:
    client = ReserveAmericaClient()
    # No rate limiting here: this test is only about which pool the calls use.
    client._limiter.interval = 0
    with patch.object(client, "_fetch_window", side_effect=_slow_fetch):
        parks = [
            asyncio.create_task(client.get_availability(
                str(400000 + i), "park", "OR", date(2026, 7, 1), date(2026, 7, 2),
            ))
            for i in range(8)
        ]
        await asyncio.sleep(0.05)  # let the provider calls reach their threads
        latency = await _dns_style_latency()
        await asyncio.gather(*parks)

    assert latency < PROVIDER_CALL_S / 2, (
        f"DNS-style call waited {latency:.2f}s behind ReserveAmerica threads"
    )


async def test_goingtocamp_calls_leave_default_executor_free(
    one_cpu_default_executor,
) -> None:
    client = GoingToCampClient()

    def slow_park(*_args, **_kwargs):
        time.sleep(PROVIDER_CALL_S)

    with patch.object(client, "_get_availability_sync", side_effect=slow_park):
        parks = [
            asyncio.create_task(client.get_availability(
                -2147483000 - i, date(2026, 7, 1), date(2026, 7, 2),
            ))
            for i in range(8)
        ]
        await asyncio.sleep(0.05)
        latency = await _dns_style_latency()
        await asyncio.gather(*parks)

    assert latency < PROVIDER_CALL_S / 2, (
        f"DNS-style call waited {latency:.2f}s behind GoingToCamp threads"
    )

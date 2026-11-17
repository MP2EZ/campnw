"""Thread pool and rate limiter for the blocking (curl_cffi) providers.

asyncio's default executor has min(32, cpu + 4) workers: 5 on prod's single
CPU. DNS lookups (``loop.getaddrinfo``, which httpx uses for Recreation.gov and
the PostHog proxy) and every ``asyncio.to_thread`` caller share it. When
ReserveAmerica and GoingToCamp calls ran there, slow parks held every worker
and DNS queued behind them for over a minute (the Oregon stall, 2026-11-07).
Provider calls get their own pool so that can't happen.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

# Matches the search fan-out (8 campgrounds at once). Threads are cheap; this
# only has to be enough that providers don't queue behind each other.
PROVIDER_WORKERS = 8


_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()


def _provider_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadPoolExecutor(
                    max_workers=PROVIDER_WORKERS, thread_name_prefix="provider",
                )
    return _pool


async def run_blocking[T](fn: Callable[..., T], /, *args: object) -> T:
    """Run a blocking provider call on the provider pool, not the default one."""
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    return await loop.run_in_executor(
        _provider_pool(), functools.partial(ctx.run, fn, *args),
    )


class MinIntervalLimiter:
    """Spaces calls at least ``interval`` seconds apart across all callers.

    One instance per provider client, and the server holds one client per
    provider, so the limit is app-wide: concurrent searches and the watch
    poller share it. A caller cancelled while waiting uses up no slot.

    A background caller (``background()`` true) takes a slot only when no
    foreground caller is waiting, so work nobody is waiting on runs in the
    gaps and never queues ahead of a search. ``background`` is checked again
    on every wake, so a job a search joins turns foreground mid-wait.
    """

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last = float("-inf")
        self._lock = asyncio.Lock()
        self._foreground_waiting = 0

    async def wait(self, background: Callable[[], bool] | None = None) -> None:
        while background is not None and background():
            if self._foreground_waiting:
                delay = max(self.interval, 0.01)
            else:
                delay = self._last + self.interval - time.monotonic()
                if delay <= 0:
                    self._last = time.monotonic()
                    return
            await asyncio.sleep(delay)

        self._foreground_waiting += 1
        try:
            async with self._lock:
                delay = self._last + self.interval - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                self._last = time.monotonic()
        finally:
            self._foreground_waiting -= 1

"""Oregon (ReserveAmerica) availability, cached per 14-day window.

ReserveAmerica answers one 14-night window per request, at most 50 sites a
page, under an app-wide 1 req/s limit. A month search for a big park is 20+
requests, so a search used to lose a park's whole fetch when the deadline cut
it, and could only reuse a cached park for the exact span it was fetched for.

Each finished window is now stored on its own (``ra_window_cache``). A park is
assembled from the fresh windows that hold its requested nights, and only the
nights none of them hold are fetched, so a search for Feb 6-19 uses a fetch of
Feb 5-18 and pays for Feb 19 alone.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pnw_campsites.providers.reserveamerica import count_requests, window_cover
from pnw_campsites.registry.models import Campground, CampgroundAvailability

logger = logging.getLogger(__name__)

# How old a stored window may be and still answer a search or a watch poll.
# The same 10 minutes the availability cache has always used.
CACHE_TTL_S = 600.0
# Stale windows are deleted on write, at most this often.
PRUNE_EVERY_S = 60.0
# Windows nobody waits on, running or queued, kept at once. About two cold
# Oregon month searches' worth of cut parks; past it, a cut park is a timeout.
BACKGROUND_MAX_WINDOWS = 24
# A queued window not started within this long is dropped: nobody asked for it
# recently, and it would be stale soon after it landed.
QUEUE_MAX_AGE_S = 300.0

Window = tuple[date, date]


@dataclass(frozen=True)
class CachedWindow:
    arrival: date
    departure: date
    fetched_at: datetime
    availability: CampgroundAvailability

    def holds(self, night: date) -> bool:
        return self.arrival <= night <= self.departure


@dataclass
class Plan:
    use: list[CachedWindow]  # stored windows that answer some requested night
    fetch: list[Window]  # windows to request for the rest
    join: list[Window] = field(default_factory=list)  # windows already on their way


def plan(
    nights: list[date], rows: list[CachedWindow], end: date,
    pending: Iterable[Window] = (),
) -> Plan:
    """Which stored windows answer the nights, which windows already being
    fetched to wait for, and which windows to fetch.

    Each night is answered by the newest row holding it, else by a pending
    window holding it. The rest get ``window_cover``'s minimal set of windows,
    clipped at ``end``.
    """
    pending = sorted(pending)
    use: dict[int, CachedWindow] = {}
    join: list[Window] = []
    missing: list[date] = []
    for night in nights:
        holders = [r for r in rows if r.holds(night)]
        if holders:
            newest = max(holders, key=lambda r: r.fetched_at)
            use[id(newest)] = newest
            continue
        coming = next((w for w in pending if w[0] <= night <= w[1]), None)
        if coming is None:
            missing.append(night)
        elif coming not in join:
            join.append(coming)
    return Plan(
        use=sorted(use.values(), key=lambda r: (r.arrival, r.fetched_at)),
        fetch=window_cover(missing, end),
        join=join,
    )


def merge(facility_id: str, windows: list[CachedWindow]) -> CampgroundAvailability:
    """One park from several windows: every site, every night. Where windows
    overlap, the newer one's status and site details win."""
    campsites = {}
    for window in sorted(windows, key=lambda w: w.fetched_at):
        for site_id, site in window.availability.campsites.items():
            earlier = campsites.get(site_id)
            merged = site.model_copy(deep=True)
            if earlier is not None:
                merged.availabilities = {**earlier.availabilities, **site.availabilities}
            campsites[site_id] = merged
    return CampgroundAvailability(facility_id=facility_id, campsites=campsites)


@dataclass
class _Job:
    """One window being fetched. Foreground while anyone waits on it."""

    task: asyncio.Task
    waiters: int = 0
    requests: int = 0

    def background(self) -> bool:
        return self.waiters == 0


@dataclass
class _Queued:
    campground: Campground
    window: Window
    queued_at: float


class OregonWindows:
    """Fetches Oregon parks window by window through the shared window cache.

    One instance per process (``api.py``), shared by searches and the watch
    poller. Each window fetch is a job owned here, not by the caller:
    - callers wanting the same window wait on the same job;
    - a caller that stops waiting (deadline, closed tab) doesn't stop the job,
      which finishes at background priority into the cache;
    - windows a cut park never started are queued and fetched one at a time.
    Jobs and queued windows nobody waits on are capped at ``max_background``.
    """

    def __init__(
        self, client, watch_db=None, *, ttl_s: float = CACHE_TTL_S,
        max_background: int = BACKGROUND_MAX_WINDOWS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._db = watch_db
        self._ttl_s = ttl_s
        self._max_background = max_background
        self._clock = clock
        self._pruned_at = float("-inf")
        self._jobs: dict[tuple[str, date, date], _Job] = {}
        self._queue: deque[_Queued] = deque()
        self._worker: asyncio.Task | None = None

    async def park(
        self, campground: Campground, nights: list[date], end: date,
    ) -> CampgroundAvailability:
        """Availability for ``nights`` at one park. If the caller is cancelled,
        the window in progress keeps going and the windows not yet started are
        queued, both in the background."""
        park_id = campground.facility_id
        started = time.monotonic()
        p = plan(nights, self._stored(park_id, nights), end, self._pending(park_id))
        windows = list(p.use)
        todo = p.join + p.fetch
        requests = 0
        outcome = "cancelled"
        try:
            for i, (arrival, departure) in enumerate(todo):
                try:
                    window, job = await self._window(campground, arrival, departure)
                except asyncio.CancelledError:
                    self.enqueue_background(campground, todo[i + 1:])
                    raise
                windows.append(window)
                if (arrival, departure) in p.fetch:
                    requests += job.requests
            result = merge(park_id, windows)
            outcome = f"{len(result.campsites)} sites"
            return result
        except Exception as exc:
            outcome = type(exc).__name__
            raise
        finally:
            logger.info(
                "ReserveAmerica %s: %d windows (%d cached, %d joined, %d fetched), "
                "%d requests in %.1fs (%s)",
                park_id, len(p.use) + len(todo), len(p.use), len(p.join), len(p.fetch),
                requests, time.monotonic() - started, outcome,
            )

    def is_pending(self, park_id: str) -> bool:
        """Whether any window of the park is being fetched or queued."""
        return bool(self._pending(park_id))

    def enqueue_park(self, campground: Campground, nights: list[date], end: date) -> None:
        """Queue a park a search wanted but never started: the windows its
        nights need that nothing stored or pending already covers."""
        park_id = campground.facility_id
        p = plan(nights, self._stored(park_id, nights), end, self._pending(park_id))
        self.enqueue_background(campground, p.fetch)

    def enqueue_background(self, campground: Campground, windows: list[Window]) -> None:
        """Queue windows to fetch when nobody else needs the limiter. Windows
        past the background cap are dropped."""
        dropped = 0
        for window in windows:
            if self._background_count() >= self._max_background:
                dropped += 1
                continue
            self._queue.append(_Queued(campground, window, self._clock()))
        if dropped:
            logger.info(
                "ReserveAmerica %s: background full, %d windows dropped",
                campground.facility_id, dropped,
            )
        if self._queue and (self._worker is None or self._worker.done()):
            self._worker = asyncio.create_task(self._drain())

    async def idle(self) -> None:
        """Wait until nothing is running or queued (tests, shutdown)."""
        while self._jobs or self._queue or (self._worker and not self._worker.done()):
            await asyncio.gather(
                *(j.task for j in list(self._jobs.values())),
                *([self._worker] if self._worker else []),
                return_exceptions=True,
            )
            await asyncio.sleep(0)

    async def aclose(self) -> None:
        """Cancel every job and drop the queue. Called on shutdown."""
        self._queue.clear()
        tasks = [j.task for j in self._jobs.values()]
        if self._worker:
            tasks.append(self._worker)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._jobs.clear()

    async def _window(
        self, campground: Campground, arrival: date, departure: date,
    ) -> tuple[CachedWindow, _Job]:
        key = (campground.facility_id, arrival, departure)
        job = self._jobs.get(key) or self._start(campground, key)
        job.waiters += 1
        try:
            return await asyncio.shield(job.task), job
        finally:
            job.waiters -= 1
            if job.waiters == 0 and not job.task.done():
                self._orphaned(key, job)

    def _start(self, campground: Campground, key: tuple[str, date, date]) -> _Job:
        job = _Job(task=None)  # type: ignore[arg-type]
        job.task = asyncio.create_task(self._run(campground, key, job))
        self._jobs[key] = job

        def done(task: asyncio.Task) -> None:
            self._jobs.pop(key, None)
            if not task.cancelled():
                task.exception()  # retrieved: a background failure is logged in _run

        job.task.add_done_callback(done)
        return job

    def _orphaned(self, key: tuple[str, date, date], job: _Job) -> None:
        """A job lost its last waiter: finish it in the background, or cancel
        it if the background is full (it counts itself)."""
        if self._background_count() > self._max_background:
            logger.info("ReserveAmerica %s %s: background full, cancelled", key[0], key[1])
            job.task.cancel()

    def _background_count(self) -> int:
        running = sum(1 for j in self._jobs.values() if j.background() and not j.task.done())
        return running + len(self._queue)

    def _pending(self, park_id: str) -> list[Window]:
        running = [(a, d) for (p, a, d) in self._jobs if p == park_id]
        queued = [q.window for q in self._queue if q.campground.facility_id == park_id]
        return running + queued

    async def _run(
        self, campground: Campground, key: tuple[str, date, date], job: _Job,
    ) -> CachedWindow:
        park_id, arrival, departure = key
        fetched_at = datetime.now()
        started = time.monotonic()
        outcome = "cancelled"
        with count_requests() as requests:
            try:
                availability = await self._client.get_window(
                    park_id, campground.booking_url_slug, campground.state,
                    arrival, departure, background=job.background,
                )
                window = CachedWindow(arrival, departure, fetched_at, availability)
                self._store(park_id, window)
                outcome = "cached"
                return window
            except Exception as exc:
                outcome = type(exc).__name__
                raise
            finally:
                job.requests = requests[0]
                if job.background():
                    logger.info(
                        "ReserveAmerica %s %s: background window, %d requests in %.1fs (%s)",
                        park_id, arrival, requests[0], time.monotonic() - started, outcome,
                    )

    async def _drain(self) -> None:
        """Fetch queued windows one at a time, oldest first."""
        while self._queue:
            q = self._queue.popleft()
            if self._clock() - q.queued_at > QUEUE_MAX_AGE_S:
                continue
            key = (q.campground.facility_id, *q.window)
            if key in self._jobs or self._is_stored(key[0], q.window):
                continue
            job = self._start(q.campground, key)
            try:
                await asyncio.shield(job.task)
            except asyncio.CancelledError:
                if not job.task.cancelled():
                    raise  # the worker itself was cancelled
            except Exception:
                pass  # logged in _run; move on to the next window

    def _is_stored(self, park_id: str, window: Window) -> bool:
        nights = [window[0] + timedelta(days=i) for i in range((window[1] - window[0]).days + 1)]
        return not plan(nights, self._stored(park_id, nights), window[1]).fetch

    def _stored(self, park_id: str, nights: list[date]) -> list[CachedWindow]:
        """Fresh stored windows for the nights. A cache problem is a miss."""
        if self._db is None or not nights:
            return []
        try:
            return [
                CachedWindow(a, d, at, CampgroundAvailability.model_validate_json(payload))
                for a, d, at, payload in self._db.get_ra_windows(
                    park_id, min(nights), max(nights), max_age_s=self._ttl_s,
                )
            ]
        except Exception:
            logger.debug("ReserveAmerica window cache read failed", exc_info=True)
            return []

    def _store(self, park_id: str, window: CachedWindow) -> None:
        if self._db is None:
            return
        try:
            self._db.put_ra_window(
                park_id, window.arrival, window.departure,
                window.availability.model_dump_json(), window.fetched_at,
            )
            if time.monotonic() - self._pruned_at >= PRUNE_EVERY_S:
                self._pruned_at = time.monotonic()
                self._db.prune_ra_windows(self._ttl_s)
        except Exception:
            logger.debug("ReserveAmerica window cache write failed", exc_info=True)

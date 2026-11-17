"""Background work yields the ReserveAmerica limiter to everyone else.

Oregon requests share one app-wide 1 req/s limit. Window fetches nobody is
waiting on anymore (a search hit its deadline, a tab closed) will finish in
the background, and must never queue ahead of a live search or a watch poll.
"""

from __future__ import annotations

import asyncio
import time

from pnw_campsites.providers.blocking import MinIntervalLimiter


async def within(aw, seconds: float = 2.0):
    """Await with a ceiling, so a regression fails instead of hanging."""
    return await asyncio.wait_for(aw, seconds)


class TestLimiterLanes:
    async def test_background_waits_for_a_later_foreground_caller(self) -> None:
        limiter = MinIntervalLimiter(0.05)
        order: list[str] = []
        await limiter.wait()  # the slot is now taken for 50 ms

        async def take(name: str, background=None) -> None:
            await limiter.wait(background=background)
            order.append(name)

        bg = asyncio.create_task(take("bg", background=lambda: True))
        await asyncio.sleep(0.01)
        fg = asyncio.create_task(take("fg"))
        await within(asyncio.gather(bg, fg))
        assert order == ["fg", "bg"]

    async def test_background_runs_when_nobody_else_waits(self) -> None:
        limiter = MinIntervalLimiter(0)
        await asyncio.wait_for(limiter.wait(background=lambda: True), 0.5)

    async def test_spacing_holds_across_both_lanes(self) -> None:
        limiter = MinIntervalLimiter(0.03)
        starts: list[float] = []

        async def take(background=None) -> None:
            await limiter.wait(background=background)
            starts.append(time.monotonic())

        await within(asyncio.gather(
            take(), take(background=lambda: True), take(), take(background=lambda: True),
        ))
        gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
        assert all(g >= 0.025 for g in gaps), gaps

    async def test_a_job_that_turns_foreground_stops_yielding(self) -> None:
        limiter = MinIntervalLimiter(0.05)
        await limiter.wait()
        flag = {"bg": True}
        waiting = asyncio.create_task(limiter.wait(background=lambda: flag["bg"]))
        await asyncio.sleep(0.01)
        flag["bg"] = False
        await asyncio.wait_for(waiting, 0.5)

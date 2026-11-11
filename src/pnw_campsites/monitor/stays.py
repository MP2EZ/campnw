"""Which stays a watch alerts on: runs of min_nights consecutive open nights.

Pure date logic. Nights are ISO dates (YYYY-MM-DD) a site is Available on,
already narrowed to the watch's range and days of week, as search narrows
them before `_find_consecutive_windows`: a Fri/Sat filter makes Fri+Sat a
run and leaves Sun out of it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


def _night_after(night: str, n: int) -> str:
    return (date.fromisoformat(night) + timedelta(days=n)).isoformat()


def stay_starts(nights: Iterable[str], min_nights: int) -> set[str]:
    """First nights of every stay of `min_nights` consecutive open nights."""
    length = max(1, min_nights)
    open_nights = set(nights)
    return {
        night for night in open_nights
        if all(_night_after(night, i) in open_nights for i in range(1, length))
    }


def new_stay_nights(
    current: Iterable[str], previous: Iterable[str], min_nights: int,
) -> list[str]:
    """Nights of stays that are open now and weren't at the last poll.

    A stay is identified by its first night, so the same stay never alerts
    twice, while a night that completes a stay (or extends a run into a new
    one) does. With min_nights 1 this is simply the newly open nights.
    """
    length = max(1, min_nights)
    new_starts = stay_starts(current, length) - stay_starts(previous, length)
    return sorted({
        _night_after(start, i) for start in new_starts for i in range(length)
    })

"""Time source (KB §6.6 reproducibility; tools.md: NTP is the world clock).

The store never calls `datetime.now()` directly — it stamps rows from an injected
`Clock`. `WallClock` for local dev; a `FixedClock` (or a future `NtpClock` backed
by the shared Time service) makes a run replayable.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class WallClock:
    """Real wall-clock UTC. Correct, but not replayable."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Deterministic clock for tests/replay: starts at `start` and advances by
    `step` on every read, so ordering is stable and reproducible."""

    def __init__(
        self,
        start: datetime | None = None,
        step: timedelta = timedelta(seconds=1),
    ) -> None:
        self._t = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self._step = step

    def now(self) -> datetime:
        t = self._t
        self._t = self._t + self._step
        return t


def http_time_fetcher(url: str) -> Callable[[], datetime]:
    """Build a fetcher that reads world time from the shared time service (NTP).

    tools.md names a global "NTP" time system for the world. Its wire contract
    isn't fixed yet, so we accept the common shapes (`sim_time`/`now`/`time`) and
    isolate that behind this one function — swap it, not the clock, when the
    contract lands.
    """

    def fetch() -> datetime:
        import httpx

        data = httpx.get(url, timeout=5.0).json()
        raw = data.get("sim_time") or data.get("now") or data.get("time")
        if not raw:
            raise ValueError(f"time service {url} returned no timestamp: {data}")
        return datetime.fromisoformat(raw)

    return fetch


class NtpClock:
    """World clock backed by the shared time service (tools.md).

    Syncs a base world time via `fetch` once (lazily / re-syncable) and advances
    it by real elapsed monotonic time between reads — so timestamps stay ordered
    and cheap without an HTTP call per message.
    """

    def __init__(self, fetch: Callable[[], datetime], resync_seconds: float = 30.0) -> None:
        self._fetch = fetch
        self._resync = resync_seconds
        self._base: datetime | None = None
        self._base_monotonic = 0.0

    def _sync(self) -> None:
        self._base = self._fetch()
        self._base_monotonic = time.monotonic()

    def now(self) -> datetime:
        if self._base is None or (time.monotonic() - self._base_monotonic) > self._resync:
            self._sync()
        assert self._base is not None
        return self._base + timedelta(seconds=time.monotonic() - self._base_monotonic)

"""Id + sequence generation (KB §6.6 reproducibility).

`seq` is the single monotonic order cursor used for both `since` polling and
replay. `UuidFactory` (default) is non-deterministic; `SeededIdFactory` yields a
deterministic id/seq sequence per run so a replay with the same seed reproduces
identical channels, messages, and ordering.
"""
from __future__ import annotations

from typing import Protocol

from packages.schemas.base import new_id


class IdFactory(Protocol):
    def new(self, prefix: str) -> str: ...
    def next_seq(self) -> int: ...


class UuidFactory:
    """Production default: random ids via the shared `new_id`, monotonic seq."""

    def __init__(self) -> None:
        self._seq = 0

    def new(self, prefix: str) -> str:
        return new_id(prefix)

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq


class SeededIdFactory:
    """Deterministic ids/seq for tests and replay: `msg_000001`, `chan_000001`…"""

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._counters: dict[str, int] = {}
        self._seq = 0

    def new(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}_{self._seed:02d}{n:06d}"

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

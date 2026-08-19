"""Active state (KB §2.3) — the hot, frequently-read/written data kept in Redis.

Postgres/SQLite remain the source of truth; Redis just makes the busy paths fast:

- **channel roster** — read-through cache of a channel's members (every send fans
  out to the roster; every read checks membership). Invalidated on membership change.
- **unread counters** — per `(agent, channel)`, bumped when a message is delivered
  to that agent and reset when the agent reads the channel. This is genuine live
  state Redis is built for; it is derived, so losing it is harmless.

`NullCache` (the default) makes all of this a no-op, so the service behaves
identically with no Redis — tests and local dev need no broker. `redis` is
imported lazily.
"""
from __future__ import annotations

import json
from typing import Protocol


class Cache(Protocol):
    def get_members(self, channel: str) -> list[str] | None: ...
    def set_members(self, channel: str, members: list[str]) -> None: ...
    def invalidate_members(self, channel: str) -> None: ...
    def bump_unread(self, agent_id: str, channel: str, by: int = 1) -> None: ...
    def reset_unread(self, agent_id: str, channel: str) -> None: ...
    def unread(self, agent_id: str) -> dict[str, int]: ...


class NullCache:
    """Default: no caching. The store is always consulted; counters are dropped."""

    def get_members(self, channel: str) -> list[str] | None:
        return None

    def set_members(self, channel: str, members: list[str]) -> None:
        return None

    def invalidate_members(self, channel: str) -> None:
        return None

    def bump_unread(self, agent_id: str, channel: str, by: int = 1) -> None:
        return None

    def reset_unread(self, agent_id: str, channel: str) -> None:
        return None

    def unread(self, agent_id: str) -> dict[str, int]:
        return {}


class RedisCache:
    """Redis-backed active state. Keys:
      chat:roster:<channel>   -> JSON list of members (TTL, read-through)
      chat:unread:<agent>     -> hash {channel: count}
    """

    def __init__(self, url: str = "redis://localhost:6379/0", roster_ttl: int = 300) -> None:
        self._url = url
        self._ttl = roster_ttl
        self._client = None

    def _conn(self):
        if self._client is None:
            import redis  # lazy: only needed when a cache is actually configured

            self._client = redis.Redis.from_url(self._url, decode_responses=True)
        return self._client

    def get_members(self, channel: str) -> list[str] | None:
        raw = self._conn().get(f"chat:roster:{channel}")
        return json.loads(raw) if raw is not None else None

    def set_members(self, channel: str, members: list[str]) -> None:
        self._conn().set(f"chat:roster:{channel}", json.dumps(members), ex=self._ttl)

    def invalidate_members(self, channel: str) -> None:
        self._conn().delete(f"chat:roster:{channel}")

    def bump_unread(self, agent_id: str, channel: str, by: int = 1) -> None:
        self._conn().hincrby(f"chat:unread:{agent_id}", channel, by)

    def reset_unread(self, agent_id: str, channel: str) -> None:
        self._conn().hdel(f"chat:unread:{agent_id}", channel)

    def unread(self, agent_id: str) -> dict[str, int]:
        raw = self._conn().hgetall(f"chat:unread:{agent_id}")
        return {k: int(v) for k, v in raw.items()}

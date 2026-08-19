"""Active state (Redis): roster read-through + unread counters, wired via the service.

Uses an in-memory `Cache` so the behaviour is verified with no Redis; `RedisCache`
itself is exercised against a fake client below."""
from __future__ import annotations

from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.integration.cache import RedisCache


class DictCache:
    """In-memory Cache implementation for tests."""

    def __init__(self) -> None:
        self.rosters: dict[str, list[str]] = {}
        self.counts: dict[str, dict[str, int]] = {}

    def get_members(self, channel):
        return self.rosters.get(channel)

    def set_members(self, channel, members):
        self.rosters[channel] = list(members)

    def invalidate_members(self, channel):
        self.rosters.pop(channel, None)

    def bump_unread(self, agent_id, channel, by=1):
        self.counts.setdefault(agent_id, {})
        self.counts[agent_id][channel] = self.counts[agent_id].get(channel, 0) + by

    def reset_unread(self, agent_id, channel):
        self.counts.get(agent_id, {}).pop(channel, None)

    def unread(self, agent_id):
        return dict(self.counts.get(agent_id, {}))


def test_unread_bumps_on_send_and_resets_on_read(store, registry, publisher):
    svc = InternalMessagingService(store, registry, publisher, DictCache())
    ch = svc.create_channel("COO-1", "incident", ["EMP-QA-17"], name="ht").channel

    svc.send_message("COO-1", ch, "please report @EMP-QA-17")
    assert svc.unread("EMP-QA-17") == {ch: 1}     # recipient gains one unread
    assert svc.unread("COO-1") == {}              # the sender never counts its own

    svc.read_channel("EMP-QA-17", ch)
    assert svc.unread("EMP-QA-17") == {}          # reset once the agent reads


def test_roster_is_cached_and_invalidated(store, registry, publisher):
    cache = DictCache()
    svc = InternalMessagingService(store, registry, publisher, cache)
    ch = svc.create_channel("COO-1", "group", ["EMP-QA-17"], name="g").channel

    svc.send_message("COO-1", ch, "hi")           # fans out -> populates roster cache
    assert set(cache.rosters[ch]) == {"COO-1", "EMP-QA-17"}

    svc.add_member("COO-1", ch, "CEO-1")          # roster changed -> cache invalidated
    assert ch not in cache.rosters


# --- RedisCache against a fake redis client (no server needed) ---

class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict = {}
        self.h: dict = {}

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None):
        self.kv[k] = v

    def delete(self, k):
        self.kv.pop(k, None)
        self.h.pop(k, None)

    def hincrby(self, k, f, by):
        self.h.setdefault(k, {})
        self.h[k][f] = int(self.h[k].get(f, 0)) + by
        return self.h[k][f]

    def hdel(self, k, f):
        self.h.get(k, {}).pop(f, None)

    def hgetall(self, k):
        return dict(self.h.get(k, {}))


def test_rediscache_roster_and_unread():
    rc = RedisCache()
    rc._client = FakeRedis()          # inject fake, bypass lazy real connection

    rc.set_members("c1", ["a", "b"])
    assert rc.get_members("c1") == ["a", "b"]
    rc.invalidate_members("c1")
    assert rc.get_members("c1") is None

    rc.bump_unread("a", "c1")
    rc.bump_unread("a", "c1")
    rc.bump_unread("a", "c2")
    assert rc.unread("a") == {"c1": 2, "c2": 1}
    rc.reset_unread("a", "c1")
    assert rc.unread("a") == {"c2": 1}

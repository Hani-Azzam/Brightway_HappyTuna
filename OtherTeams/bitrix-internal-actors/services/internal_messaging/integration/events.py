"""Event plane (KB §1.2 activation, §2.4 event sourcing).

Chat emits one event per message; it does NOT decide who reacts — the activation
layer/Director consumes these and wakes the right agent. The body is NOT in the
event (content plane vs event plane); consumers follow `message_id` back via a
read. `recipients` = current channel members, so an agent can never receive an
event for a channel it isn't in (CEO isolation by construction).

Two layers:
- `Publisher` — what the service calls (`NullPublisher` default → chat works via
  `since` polling before any bus exists).
- `Bus` — the transport a `BusPublisher` fans out to. `InMemoryBus` for tests,
  `RedisStreamsBus` for the real deployment (Redis is already in the compose).

Delivery is **per-recipient**: the event is written to one subject/stream per
member (`chat.inbox.<agent_id>`), so the ACL is by construction — an agent only
ever reads its own inbox.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ChatMessagePosted:
    event_type: str
    actor_id: str
    sim_time: str
    seq: int
    channel: str
    message_id: str
    mentions: list[str] = field(default_factory=list)
    trust_label: str = "internal"
    correlation_id: str | None = None
    recipients: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return asdict(self)


# --- Publisher (what the service calls) -------------------------------------


class Publisher(Protocol):
    def publish(self, event: ChatMessagePosted) -> None: ...


class NullPublisher:
    """Default: drop events. Chat stays usable via `since` polling."""

    def publish(self, event: ChatMessagePosted) -> None:  # noqa: D401
        return None


class RecordingPublisher:
    """Captures events in-memory (tests, or a future drain-to-bus adapter)."""

    def __init__(self) -> None:
        self.events: list[ChatMessagePosted] = []

    def publish(self, event: ChatMessagePosted) -> None:
        self.events.append(event)


# --- Bus (the transport a BusPublisher fans out to) -------------------------

_INBOX_PREFIX = "chat.inbox."       # per-recipient subject
_STREAM = "chat.message_posted"     # global stream for audit/replay/Director


class Bus(Protocol):
    def publish(self, subject: str, payload: dict) -> None: ...


class InMemoryBus:
    """Fake bus for tests: records payloads per subject."""

    def __init__(self) -> None:
        self.published: dict[str, list[dict]] = {}

    def publish(self, subject: str, payload: dict) -> None:
        self.published.setdefault(subject, []).append(payload)


class RedisStreamsBus:
    """Redis Streams transport (the `redis` service is already in the compose).

    Ordered, persistent, replayable, multi-language — a good fit for a research
    sim (no Kafka). `redis` is imported lazily so importing this module never
    requires a running broker.
    """

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._url = url
        self._client = None

    def _conn(self):
        if self._client is None:
            import redis  # lazy: only needed when actually publishing

            self._client = redis.Redis.from_url(self._url)
        return self._client

    def publish(self, subject: str, payload: dict) -> None:
        # subject becomes the stream key; one field carries the JSON event.
        self._conn().xadd(subject, {"event": json.dumps(payload)})


class BusPublisher:
    """Fan the event out to each recipient's inbox subject + a global stream.

    Per-recipient delivery makes the CEO-isolation ACL structural: an agent's
    inbox only ever contains events for channels it belongs to.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    def publish(self, event: ChatMessagePosted) -> None:
        payload = event.to_payload()
        for agent_id in event.recipients:
            self._bus.publish(f"{_INBOX_PREFIX}{agent_id}", payload)
        # A global stream for the Director / audit / replay (not agent-readable).
        self._bus.publish(_STREAM, payload)


class KafkaPublisher:
    """Publish `chat.message_posted` to a **Kafka** topic — a durable, partitioned,
    replayable event log (KB §2.3/§2.4).

    Unlike the per-subject `BusPublisher`, Kafka uses one topic with the **channel
    as the message key**, so all events for a channel land on one partition and stay
    ordered. `recipients` travels in the payload, so a per-agent consumer can still
    filter to its own inbox (and the Director sees the whole ordered log for replay).

    The producer (`confluent_kafka`) is created lazily so importing this module
    never requires the driver or a running broker.
    """

    def __init__(self, brokers: str, topic: str = _STREAM) -> None:
        self._brokers = brokers
        self._topic = topic
        self._producer = None

    def _prod(self):
        if self._producer is None:
            from confluent_kafka import Producer  # lazy

            self._producer = Producer({"bootstrap.servers": self._brokers})
        return self._producer

    def publish(self, event: ChatMessagePosted) -> None:
        p = self._prod()
        p.produce(
            self._topic,
            key=event.channel.encode(),          # per-channel ordering
            value=json.dumps(event.to_payload()).encode(),
        )
        p.poll(0)                                 # serve delivery callbacks
        p.flush(5)                                # ensure it lands (sim scale)

"""Event publishing — the one way messages leave this service for the bus.

Defines an abstract `EventPublisher` plus two implementations:
  - `KafkaPublisher`     real broker, used when the service runs.
  - `InMemoryPublisher`  captures events in a list, used by tests.

Everything upstream depends on the *abstract* `EventPublisher`, so swapping the
real broker for the fake one in tests needs zero code changes in the service.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from aiokafka import AIOKafkaProducer


class EventPublisher(ABC):
    """The seam between 'we decided to emit an event' and 'how it actually ships'."""

    @abstractmethod
    async def publish(self, topic: str, event: dict) -> None: ...


class KafkaPublisher(EventPublisher):
    """Ships events to a real Kafka broker.

    `start()`/`stop()` manage the producer's network connection and are called
    once from the app's lifespan (see app/main.py) — not per request.
    """

    def __init__(self, bootstrap_servers: str) -> None:
        self._servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=self._servers)
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def publish(self, topic: str, event: dict) -> None:
        assert self._producer is not None, "KafkaPublisher.start() was never called"
        # send_and_wait blocks until the broker acks, so a failure here raises —
        # the outbox relay upstream relies on that to know delivery did not happen.
        await self._producer.send_and_wait(topic, json.dumps(event).encode())


class InMemoryPublisher(EventPublisher):
    """Test double. Records every (topic, event) so tests can assert on them."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, topic: str, event: dict) -> None:
        self.events.append((topic, event))

    def clear(self) -> None:
        self.events.clear()

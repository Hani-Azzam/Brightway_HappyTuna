"""Client for listening to the event generator.

Becoming a subscriber is one loop:

    from event_client import subscribe

    async for event in subscribe("press"):
        await my_agent(event.text)

Pass several tags to follow more than one channel, or none to receive
everything:

    async for event in subscribe("press", "regulator"):
        ...

Everything the transport needs - the no-read-timeout setting, skipping keepalive
comments, unwrapping the JSON envelope, and reconnecting when the stream drops -
is handled here so an agent never has to think about it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = os.getenv("EVENT_GENERATOR_URL", "http://localhost:8006")

# Inside the Docker network this should be http://event-generator:8000 - set
# EVENT_GENERATOR_URL in the service's environment rather than editing this.

# The stream idles for long stretches by design, so reads must never time out.
# The other phases still fail fast, so a wrong URL is an immediate error rather
# than a hang.
_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)


@dataclass(frozen=True)
class Event:
    """One event off the feed.

    `seq` counts every event the server emitted, not just the ones you receive -
    so a tag-filtered subscriber sees gaps. That is normal, and it is how a real
    gap (a dropped event) can be told apart from "not for me".
    """

    tag: str
    text: str
    seq: int
    ts: float


async def subscribe(
    *tags: str,
    url: str | None = None,
    reconnect_seconds: float | None = 3.0,
) -> AsyncIterator[Event]:
    """Yield events as they arrive, reconnecting if the stream drops.

    `tags` filters the feed; omit it to receive every tag. `url` defaults to
    $EVENT_GENERATOR_URL. Set `reconnect_seconds=None` to stop after the first
    disconnect instead of retrying - mainly useful in tests.
    """
    base = (url or DEFAULT_URL).rstrip("/")
    params = [("tag", tag) for tag in tags]

    async with httpx.AsyncClient() as client:
        while True:
            try:
                async for event in _stream_once(client, base, params):
                    yield event
            except httpx.HTTPError as exc:
                if reconnect_seconds is None:
                    raise
                log.warning("event stream failed (%s); reconnecting", exc)
            else:
                # Server closed the stream cleanly rather than erroring.
                if reconnect_seconds is None:
                    return
                log.info("event stream closed by server; reconnecting")

            await asyncio.sleep(reconnect_seconds)


async def _stream_once(
    client: httpx.AsyncClient, base: str, params: list[tuple[str, str]]
) -> AsyncIterator[Event]:
    """One connection's worth of events, ending when the stream closes."""
    async with client.stream(
        "GET", f"{base}/subscribe", params=params, timeout=_TIMEOUT
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            # The stream also carries blank separators and ": ping" keepalives.
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[len("data:") :].strip())
            # Read fields explicitly so a new one on the server doesn't break
            # older clients.
            yield Event(
                tag=payload["tag"],
                text=payload["text"],
                seq=payload["seq"],
                ts=payload["ts"],
            )

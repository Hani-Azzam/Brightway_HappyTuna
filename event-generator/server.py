"""HTTP front end for the event broker, so subscribers can live in other processes.

`event_broker.Event` is in-process: `subscribe()` holds a Python function and
`emit()` calls it on the caller's thread. That is fine inside one program, but
the agents that need these events run as separate services. This module wraps
the same broker in a FastAPI app and hands each HTTP subscriber a Server-Sent
Events stream, so "register a callback" becomes "hold open a GET request".

The broker itself is untouched - it is still the thing doing the fan-out, and it
is still usable directly for in-process callers and tests.

    GET  /subscribe?tag=press   open an SSE stream (repeatable; omit for all tags)
    POST /emit                  inject one event
    POST /replay                play the scripted crisis feed once
    GET  /tags                  tags the scripted feed uses
    GET  /health                liveness + current subscriber count
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from itertools import count
from typing import AsyncIterator

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from event_broker import Event
from event_generator import CRISIS_FEED, replay as replay_feed

# A slow subscriber must not grow its backlog without limit. At this depth we
# start dropping the oldest event rather than the newest, so a client that falls
# behind still ends up with the most recent state of the crisis.
QUEUE_MAXSIZE = 100

# Events are sparse - a whole replay is 5 events over ~10s, then silence. Without
# traffic, proxies and clients close idle streams, so send an SSE comment often
# enough to keep the connection considered alive.
KEEPALIVE_SECONDS = 15.0

app = FastAPI(
    title="Event Generator",
    description="Scripted crisis feed for the HappyTuna simulation, over SSE.",
)

broker = Event()

# `Event` keeps its listeners in a plain dict. Emitting already iterates a copy
# of each listener list, but subscribe/unsubscribe mutate that dict and can run
# on the request thread while a replay thread is mid-emit - so serialize the
# mutations here rather than editing the broker.
_registry_lock = threading.Lock()


# eq=False keeps the default identity hash, so live subscribers can go in a set.
@dataclass(eq=False)
class _Subscriber:
    """Per-connection state: the queue its events land in, and what it missed."""

    queue: asyncio.Queue[str]
    dropped: int = field(default=0)


_connections: set[_Subscriber] = set()


class _Sequencer:
    """Stamps each event once, then forwards it to the real broker.

    `generate()` only needs something exposing `.emit(tag, text)`, so passing
    this in its place lets every event get a sequence number and timestamp
    without touching `event_generator.py`. Stamping here rather than per
    listener matters: the same event must carry the same `seq` for every
    subscriber, otherwise the number is useless for spotting a gap.
    """

    def __init__(self, target: Event) -> None:
        self._target = target
        self._seq = count(1)

    def emit(self, tag: str, text: str) -> dict:
        envelope = {
            "tag": tag,
            "text": text,
            # next() on an itertools.count is atomic, so this is safe to call
            # from the replay thread and a request thread at the same time.
            "seq": next(self._seq),
            "ts": time.time(),
        }
        self._target.emit(tag, json.dumps(envelope))
        return envelope


sequencer = _Sequencer(broker)


def _feed_tags() -> list[str]:
    return sorted({tag for tag, _ in CRISIS_FEED})


def _offer(sub: _Subscriber, envelope: str) -> None:
    """Put one event on a subscriber's queue. Runs on the event loop thread."""
    if sub.queue.full():
        try:
            sub.queue.get_nowait()  # drop oldest to make room
            sub.dropped += 1
        except asyncio.QueueEmpty:  # drained between the check and here
            pass
    sub.queue.put_nowait(envelope)


class EmitRequest(BaseModel):
    tag: str
    text: str


@app.get("/health")
async def health() -> dict:
    with _registry_lock:
        subscribers = len(_connections)
    return {"status": "ok", "subscribers": subscribers}


@app.get("/tags")
async def tags() -> dict:
    return {"tags": _feed_tags()}


@app.post("/emit")
async def emit(request: EmitRequest) -> dict:
    """Inject a single event - this is how other services fire into the world."""
    envelope = sequencer.emit(request.tag, request.text)
    return {"status": "emitted", "seq": envelope["seq"], "tag": envelope["tag"]}


@app.post("/replay")
async def replay(delay: float = 2.0) -> dict:
    """Play the scripted crisis feed once, in the background.

    Scripted on purpose: this is the debugging path, so it must stay free and
    repeatable. `event_generator.generate()` is the LLM path and is deliberately
    not wired to an endpoint - a stray curl should never cost 24 model calls.

    `replay_feed()` is synchronous and sleeps between events, so it runs on its
    own thread - awaiting it here would block every other request for the
    duration.
    """
    threading.Thread(
        target=replay_feed, args=(sequencer,), kwargs={"delay": delay}, daemon=True
    ).start()
    return {"status": "replaying", "events": len(CRISIS_FEED), "delay": delay}


@app.get("/subscribe")
async def subscribe(tag: list[str] | None = Query(default=None)) -> StreamingResponse:
    """Open an SSE stream of events, filtered to the given tags.

    Repeat `tag` to follow several (`?tag=press&tag=social`); omit it entirely to
    receive every tag the scripted feed uses. The stream stays open until the
    client disconnects, which is also what unsubscribes it.
    """
    tags = tag or _feed_tags()
    loop = asyncio.get_running_loop()
    sub = _Subscriber(queue=asyncio.Queue(maxsize=QUEUE_MAXSIZE))

    def listener(envelope: str) -> None:
        # Fires on whichever thread emitted - usually the /replay worker, not
        # the event loop. asyncio queues are not thread-safe, so hop back onto
        # the loop before touching this subscriber's queue.
        loop.call_soon_threadsafe(_offer, sub, envelope)

    with _registry_lock:
        for name in tags:
            broker.subscribe(listener, name)
        _connections.add(sub)

    async def stream() -> AsyncIterator[bytes]:
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(
                        sub.queue.get(), timeout=KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield b": ping\n\n"  # SSE comment - ignored by clients
                    continue
                yield f"data: {envelope}\n\n".encode()
        finally:
            # Runs on client disconnect as well as normal teardown.
            # Event.unsubscribe sweeps every tag this listener sits under, so
            # one call cleans up a multi-tag subscriber completely.
            with _registry_lock:
                broker.unsubscribe(listener)
                _connections.discard(sub)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stops nginx buffering the stream
        },
    )

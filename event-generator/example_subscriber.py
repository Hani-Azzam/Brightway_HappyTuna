"""Usage example: a listener that handles only the "press" tag.

Subscribing is the two lines in main() - event_client handles the connection,
the reconnects, and unwrapping each event. Everything else in this file is the
demo around it.

To build a real listener, copy this file and change two things: the tag, and the
body of press_agent().

Run the generator first, then this script:

    docker compose up event-generator
    python example_subscriber.py
    curl -X POST http://localhost:8006/replay     # in another terminal
"""

from __future__ import annotations

import asyncio
import logging

from event_client import subscribe

TAG = "press"


async def press_agent(text: str) -> None:
    """Called once per "press" event, with the event text as its only argument.

    This is the seam for the real work: swap the print for a call to your AI
    agent and hand it `text` as the prompt. Awaiting a slow agent here delays
    the next event - if that matters, push the text onto a queue instead.
    """
    # flush because print() block-buffers when stdout isn't a terminal: piped or
    # redirected, a long-running listener otherwise looks dead for a long while.
    print(f"[press_agent] received:\n{text}\n", flush=True)


async def main() -> None:
    # Shows the client's reconnect messages; drop it and they stay silent.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # httpx logs a line per request at INFO, which is noise for a long-lived stream.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(f"Listening on tag '{TAG}'. Ctrl+C to stop.\n", flush=True)

    # Only "press" is subscribed, so this sees the six press briefings. The
    # "customer" events are still emitted, they just aren't routed here. Pass
    # more tags to follow several: subscribe("press", "customer").
    async for event in subscribe(TAG):
        await press_agent(event.text)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Closing the connection is the unsubscribe - nothing else to clean up.
        print("\nStopped listening.")

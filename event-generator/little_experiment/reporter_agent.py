"""Reporter agent: listens for "press" events and prints a short report on each.

Subscribing is the two lines in main() - event_client handles the connection,
the reconnects and unwrapping each event. The only thing added here is a call
to Claude in between.

    uvicorn server:app --port 8006                  # terminal A, from event-generator/
    python little_experiment/reporter_agent.py      # terminal B
    curl -X POST http://localhost:8006/replay       # terminal C

Needs ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import anthropic

# event_client.py sits in the parent folder and isn't an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_client import subscribe  # noqa: E402

TAG = "press"
MODEL = "claude-haiku-4-5"
SYSTEM = (
    "You are a newsroom reporter covering a food safety crisis at HappyTuna. "
    "Given a briefing, write a three sentence report: what happened, who is "
    "affected, what happens next. Hard facts from the briefing only - no "
    "speculation, no advice, no preamble."
)

client = anthropic.AsyncAnthropic()


async def report(text: str) -> str:
    """Turn one briefing into a short report."""
    response = await client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


async def main() -> None:
    # Shows the client's reconnect messages; drop it and they stay silent.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(f"Reporter listening on tag '{TAG}'. Ctrl+C to stop.\n", flush=True)

    # Awaiting the model here delays the next event. The scripted feed sends
    # press events seconds apart, so a couple of seconds of model time is fine.
    async for event in subscribe(TAG):
        print(f"--- event #{event.seq} ---", flush=True)
        print(f"{await report(event.text)}\n", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Closing the connection is the unsubscribe - nothing else to clean up.
        print("\nStopped listening.")

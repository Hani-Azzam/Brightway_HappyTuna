"""Container entrypoint: the CEO agent running continuously.

Two things wake the CEO:

1. **Press events** from the event generator (tag "press") — the public news a
   real CEO would actually see. Events arriving in a burst (e.g. a /replay of
   the scripted feed) are debounced into ONE cycle so a 12-event replay does
   not fan out into 12 full plan-solve runs of LLM calls.
2. **A periodic review** every CEO_REVIEW_INTERVAL seconds (0 disables it) —
   the CEO checks its own systems (support queue, analytics, social feed,
   internal chat) even when no news broke.

Each wake runs one plan-solve cycle of CeoAgent against the full gateway tool
surface, with sliding-window memory carrying context between cycles (see
services/memory.py). Cycles never overlap: a periodic review that fires while
an event cycle runs is skipped, not queued.

Environment knobs (all optional):
    CEO_ROLE                 gateway role to run as        (default "ceo")
    CEO_DRY_RUN              hold back writes if "true"    (default "false")
    CEO_REVIEW_INTERVAL      seconds between reviews       (default 900, 0=off)
    CEO_EVENT_DEBOUNCE       seconds to batch press events (default 20)
    CEO_MAX_PLAN_STEPS       plan length cap               (default 8)
    ANTHROPIC_API_KEY        required — the CEO's LLM (Claude Haiku)
    EVENT_GENERATOR_URL      the press feed (compose sets it)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from agents.CEO_Agent import CeoAgent, CeoConfig
from event_client import subscribe
from gateway_bridge import setup_gateway_tools, teardown_gateway_tools
from services.llm_client import LlmClient, LlmConfig
from services.memory import ConversationMemory
from services.tool_executor import ToolExecutor

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ceo.autopilot")

GATEWAY_RETRIES = 20
GATEWAY_RETRY_DELAY = 10.0

PERIODIC_BRIEF = (
    "Periodic review: nothing specific has been reported to you right now. "
    "Check the state of the company through your systems -- the support queue "
    "(especially safety_concern tickets), public sentiment and narratives on the "
    "social network, and the internal chat. Take whatever actions you judge "
    "appropriate; taking no action is acceptable if everything is calm."
)


def _event_brief(texts: list[str]) -> str:
    if len(texts) == 1:
        briefing = texts[0]
    else:
        briefing = "\n---\n".join(texts)
    return (
        "The following press briefing(s) just reached you:\n"
        f"{briefing}\n\n"
        "As CEO of HappyTuna, assess the situation using your systems (support "
        "queue, social analytics, public feed, internal chat) and respond as you "
        "judge appropriate -- internally, publicly, or both."
    )


def _connect_gateway_with_retry(executor: ToolExecutor, role: str, dry_run: bool):
    """The platforms may still be booting when this container starts; keep
    trying rather than launching a CEO with no tools.

    A partial connection is retried too: setup_gateway_tools succeeds even when
    a server is skipped (that resilience is right for a mid-simulation blip),
    but at boot "the CEO chose not to act on social" and "social wasn't up yet"
    must not look alike -- so we insist on every enabled server before starting.
    On the final attempt a partial surface is accepted rather than crash-looping.
    """
    for attempt in range(1, GATEWAY_RETRIES + 1):
        try:
            bridge = setup_gateway_tools(executor, role=role, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gateway setup failed (attempt %d/%d): %s",
                           attempt, GATEWAY_RETRIES, exc)
            time.sleep(GATEWAY_RETRY_DELAY)
            continue

        missing = [s.server_id for s in bridge.statuses if s.enabled and not s.connected]
        if not missing:
            return bridge
        if attempt == GATEWAY_RETRIES:
            logger.warning("continuing with a partial tool surface; still down: %s",
                           ", ".join(missing))
            return bridge

        logger.warning("gateway up but %s not connected yet (attempt %d/%d); retrying",
                       ", ".join(missing), attempt, GATEWAY_RETRIES)
        teardown_gateway_tools(bridge)
        time.sleep(GATEWAY_RETRY_DELAY)
    raise RuntimeError("gateway never became reachable; giving up")


async def main() -> None:
    role = os.environ.get("CEO_ROLE", "ceo")
    dry_run = os.environ.get("CEO_DRY_RUN", "false").lower() in ("1", "true", "yes")
    review_interval = float(os.environ.get("CEO_REVIEW_INTERVAL", "900"))
    debounce = float(os.environ.get("CEO_EVENT_DEBOUNCE", "20"))
    max_steps = int(os.environ.get("CEO_MAX_PLAN_STEPS", "8"))

    llm = LlmClient(LlmConfig(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        model_name=os.environ.get("CEO_MODEL_NAME", "claude-haiku-4-5"),
        temperature=float(os.environ.get("CEO_TEMPERATURE", "0.7")),
    ))

    executor = ToolExecutor(max_retries=2, base_delay=0.5)
    bridge = await asyncio.to_thread(_connect_gateway_with_retry, executor, role, dry_run)

    memory = ConversationMemory(llm)
    ceo = CeoAgent(llm, executor, CeoConfig(max_plan_steps=max_steps), memory=memory)

    cycle_lock = asyncio.Lock()

    async def run_cycle(reason: str, brief: str) -> None:
        if cycle_lock.locked():
            logger.info("skipping %s cycle: another cycle is still running", reason)
            return
        async with cycle_lock:
            logger.info("=== CEO cycle start (%s) ===", reason)
            try:
                response = await asyncio.to_thread(ceo.chat, brief)
                logger.info("=== CEO cycle done (%s) ===\n%s", reason, response)
            except Exception:
                logger.exception("CEO cycle failed (%s); continuing", reason)

    async def press_listener() -> None:
        pending: list[str] = []
        flusher: asyncio.Task | None = None

        async def flush_later() -> None:
            await asyncio.sleep(debounce)
            texts, pending[:] = list(pending), []
            if texts:
                await run_cycle(f"press x{len(texts)}", _event_brief(texts))

        async for event in subscribe("press"):
            logger.info("press event seq=%s: %s", event.seq, event.text[:100])
            pending.append(event.text)
            if flusher is None or flusher.done():
                flusher = asyncio.create_task(flush_later())

    async def periodic_review() -> None:
        if review_interval <= 0:
            return
        while True:
            await asyncio.sleep(review_interval)
            await run_cycle("periodic review", PERIODIC_BRIEF)

    logger.info("CEO autopilot up: role=%s dry_run=%s review_interval=%ss debounce=%ss",
                role, dry_run, review_interval, debounce)
    try:
        await asyncio.gather(press_listener(), periodic_review())
    finally:
        teardown_gateway_tools(bridge)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

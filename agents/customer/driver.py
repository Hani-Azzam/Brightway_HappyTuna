"""
Autonomous driver: subscribes to the event generator and reacts to crisis
events on behalf of every persona, without waiting to be called.

Drives the workflow the same way test_workflow.py does -- in-process, via
nat.runtime.loader.load_workflow -- rather than by making an MCP call to
our own "nat mcp serve" process. That would be a pointless network hop to
ourselves; load_workflow gives a direct async handle to the same decision
function nat mcp serve exposes.

Runs as its own asyncio task inside main.py, alongside "nat mcp serve" as a
subprocess. The two paths end up with separate in-memory persona state
(register.py's _memory is a plain module-level dict, and "nat mcp serve"
lives in a different OS process) -- this doubles that existing limitation
rather than introducing a new one; see register.py's note at the bottom.
"""
from __future__ import annotations

import asyncio
import logging
import os

from event_client import subscribe
from personas import all_persona_ids

import register  # noqa: F401  -- registers customer_agent_decision
import nat.plugins.mcp.register  # noqa: F401  -- registers mcp_client
from nat.runtime.loader import load_workflow

logger = logging.getLogger(__name__)

# Which event-generator tags customers should react to. The generator emits two,
# "customer" and "press" (see event-generator/event_generator.py); only
# "customer" is subscribed here, since that is what another customer would
# actually experience. Press coverage is left to the agents that handle it.
# An unknown tag means the driver connects and then silently receives nothing.
DEFAULT_EVENT_TAGS = ("customer",)


def _event_tags() -> tuple[str, ...]:
    raw = os.environ.get("CUSTOMER_AGENT_EVENT_TAGS")
    if not raw:
        return DEFAULT_EVENT_TAGS
    return tuple(tag.strip() for tag in raw.split(",") if tag.strip())


def _brief(exc: BaseException) -> str:
    """One log line instead of a 200-frame guardrails/NAT traceback."""
    message = " ".join(f"{type(exc).__name__}: {exc}".split())
    if len(message) > 300:
        message = message[:300] + " ..."
    return message


# Substrings that mean "the model provider did not answer", as opposed to a bug
# in our own decision code. Worth calling out, because the symptom otherwise
# looks like a broken agent rather than a broken upstream.
_PROVIDER_FAILURE_MARKERS = ("invoking LLM", "Timeout", "timed out", "504", "502", "429")

_PROVIDER_HINT = (
    "the model provider did not answer -- check its status page and the key in "
    ".env; the 'NIM outage escape hatch' block there repoints this agent at "
    "another OpenAI-compatible endpoint"
)


async def _react(workflow, persona_id: str, event_text: str) -> None:
    try:
        async with workflow.run({"persona_id": persona_id, "event": event_text}) as runner:
            result = await runner.result(to_type=dict)
    except Exception as exc:
        summary = _brief(exc)
        if any(marker in summary for marker in _PROVIDER_FAILURE_MARKERS):
            logger.error("persona=%s got no decision: %s -- %s", persona_id, summary, _PROVIDER_HINT)
        else:
            logger.error("persona=%s got no decision: %s", persona_id, summary)
        # Keep the full traceback available without drowning the feed in it.
        logger.debug("traceback for persona=%s", persona_id, exc_info=True)
        return

    # A rail refusal or unparseable model output arrives as a normal result with
    # `error` set. Say so instead of logging "action=None", which reads like the
    # persona chose to do nothing.
    if result.get("error"):
        logger.warning("persona=%s produced no usable decision: %s", persona_id, result["error"])
        return

    decision = result.get("decision") or {}
    ticket = result.get("ticket")
    post = result.get("post") or {}
    logger.info(
        "persona=%s action=%s ticket=%s post=%s",
        persona_id,
        decision.get("action"),
        ticket["ticket_id"] if ticket else None,
        post.get("id") or post.get("error"),
    )


async def run() -> None:
    tags = _event_tags()
    persona_ids = all_persona_ids()
    logger.info("Listening for tags %s, reacting as personas %s", tags, persona_ids)

    async with load_workflow("workflow.yml") as workflow:
        async for event in subscribe(*tags):
            logger.info("event tag=%s seq=%s: %s", event.tag, event.seq, event.text[:80])
            # Sequential, not gathered: keeps this friendly to the NIM API's
            # rate limits and avoids concurrent writers to the same _memory
            # dict entry -- a burst of 5 simultaneous LLM calls per event
            # isn't needed for a scripted 5-event demo feed.
            for persona_id in persona_ids:
                await _react(workflow, persona_id, event.text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())

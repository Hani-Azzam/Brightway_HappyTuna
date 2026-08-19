"""
Verification test for the Customer Agent NAT workflow.

Everything is REAL except the actual model call inside NeMo Guardrails
(LLMRails.generate_async), which is mocked here since it needs a live
NVIDIA_API_KEY. Real: NAT's WorkflowBuilder, the MCP function group
connecting to a real running Customer Support MCP server, persona
loading, memory updates, and the actual create_ticket tool call (a
real ticket gets created in the real SQLite-backed Customer Support
system).

Run with the Customer Support MCP server already running, e.g.:
    CS_DB_PATH=test.db MCP_PORT=8010 python ../Customer_Support_System/mcp_server.py &
    CUSTOMER_SUPPORT_MCP_URL=http://localhost:8010/mcp python test_workflow.py
"""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Match the Dockerfile's ENV exactly, rather than relying on personas.py's
# fallback (Path(__file__).parent) which only works by accident when
# personas.py and personas.yaml happen to sit in the same folder --
# true locally, NOT true once the package is actually pip-installed
# (see test_packaging.py for the regression test on that specific bug).
os.environ.setdefault("PERSONAS_CONFIG_PATH", str(Path(__file__).parent / "personas.yaml"))

import register  # noqa: F401  -- registers customer_agent_decision
import nat.plugins.mcp.register  # noqa: F401  -- registers mcp_client
from nat.runtime.loader import load_workflow


ANGRY_DECISION = {
    "action": "open_support_ticket",
    "emotion": "anger",
    "reasoning": "This is very concerning, I don't trust this batch anymore.",
    "trust_score": 0.2,
    "confidence": 0.9,
    "ticket_subject": "Concerned about contamination",
    "ticket_description": "I'm worried about batch 4471, this feels dangerous.",
    "issue_type": "safety_concern",
}

CALM_DECISION = {
    "action": "wait_for_more_information",
    "emotion": "uncertainty",
    "reasoning": "I'll wait to hear more from the company before deciding anything.",
    "trust_score": 0.6,
    "confidence": 0.7,
    "ticket_subject": None,
    "ticket_description": None,
    "issue_type": None,
}


async def main():
    mock_generate = AsyncMock(return_value={"role": "assistant", "content": json.dumps(ANGRY_DECISION)})

    with patch("nemoguardrails.LLMRails.generate_async", mock_generate):
        async with load_workflow("workflow.yml") as workflow:
            async with workflow.run({
                "persona_id": "vocal_complainer",
                "event": "Contamination reported in batch 4471",
            }) as runner:
                result = await runner.result(to_type=dict)

    print("=== Test 1: angry (mocked) decision ===")
    print("Action:", result["decision"]["action"])
    print("Ticket filed:", result["ticket"] is not None)
    if result["ticket"]:
        print("  ticket_id:", result["ticket"]["ticket_id"])
        print("  sentiment (auto-scored by real Customer Support system):", result["ticket"]["sentiment"])
        print("  issue_type:", result["ticket"]["issue_type"])
    assert result["ticket"] is not None, "Expected a ticket to be filed"

    print()
    print("=== Test 2: calm (mocked) decision -- should NOT file a ticket ===")
    mock_generate2 = AsyncMock(return_value={"role": "assistant", "content": json.dumps(CALM_DECISION)})
    with patch("nemoguardrails.LLMRails.generate_async", mock_generate2):
        async with load_workflow("workflow.yml") as workflow:
            async with workflow.run({
                "persona_id": "loyal_customer",
                "event": "Contamination reported in batch 4471",
            }) as runner:
                result2 = await runner.result(to_type=dict)
    print("Action:", result2["decision"]["action"])
    print("Ticket filed:", result2["ticket"] is not None, "(expected: False)")
    assert result2["ticket"] is None, "Expected no ticket to be filed"

    print()
    print("All checks passed.")


asyncio.run(main())
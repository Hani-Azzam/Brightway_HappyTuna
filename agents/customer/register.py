"""
Customer Agent decision function, registered as a NAT function.

Given a persona_id and an event, this:
  1. Builds the persona-specific prompt (system prompt + persona attributes + memory)
  2. Calls a NIM-hosted model THROUGH NeMo Guardrails (input rail checks the
     event is legitimate / not a jailbreak; output rail checks the response
     is valid JSON in the required schema, doesn't invent facts, and doesn't
     break character)
  3. If the decision is to open_support_ticket, calls the MCP-discovered
     create_ticket tool (customer_support__create_ticket) to file a REAL
     ticket in the Customer Support system -- no custom HTTP/MCP client code
     needed, NAT's mcp_client function group already exposes it as a callable
     function.

Per-persona memory (trust score, past decisions) is kept in-memory, keyed
by persona_id. See the note at the bottom about upgrading this later.
"""
import json
import logging

from pydantic import Field
from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from nemoguardrails import LLMRails, RailsConfig

from personas import get_persona
from system_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# In-memory per-persona state. See note at bottom of file about upgrading
# this to SQLite later, same pattern the Customer Support system used.
_memory: dict[str, dict] = {}


def _get_memory(persona_id: str, initial_trust: float) -> dict:
    return _memory.setdefault(persona_id, {
        "trust_score": initial_trust,
        "past_decisions": [],
    })


def _parse_decision(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


class CustomerAgentDecisionConfig(FunctionBaseConfig, name="customer_agent_decision"):
    """
    Customer Agent decision function. Given a persona_id and an event,
    calls a NIM-hosted model (wrapped in NeMo Guardrails input/output
    checks) to decide the customer's reaction, then files a real ticket
    via the Customer Support MCP tool if the decision is to complain.
    """
    function_group_name: str = Field(
        default="customer_support",
        description="Name of the MCP function group exposing Customer Support tools",
    )
    create_ticket_tool_name: str = Field(
        default="customer_support__create_ticket",
        description="Prefixed name of the discovered create_ticket tool within the function group",
    )
    guardrails_config_path: str = Field(
        default="guardrails_config",
        description="Path to the NeMo Guardrails config directory",
    )
    workflow_alias: str | None = Field(
        default="customer_agent_react",
        description="Name this workflow is exposed as when served via the MCP front end "
        "(nat mcp serve). Required by NAT's MCP server plugin even for non-agent workflows.",
    )


@register_function(config_type=CustomerAgentDecisionConfig)
async def customer_agent_decision(config: CustomerAgentDecisionConfig, builder: Builder):
    group = await builder.get_function_group(config.function_group_name)
    accessible_fns = await group.get_accessible_functions()
    create_ticket_fn = accessible_fns[config.create_ticket_tool_name]

    rails_config = RailsConfig.from_path(config.guardrails_config_path)
    rails = LLMRails(rails_config)

    async def _decide_and_act(persona_id: str, event: str) -> dict:
        persona = get_persona(persona_id)
        memory = _get_memory(persona_id, persona["attributes"]["trust_level"])

        user_message = json.dumps({
            "persona_attributes": persona["attributes"],
            "persona_description": persona["description"],
            "event": event,
            "memory": memory,
        }, indent=2)

        response = await rails.generate_async(messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])

        raw_text = response["content"] if isinstance(response, dict) else str(response)

        try:
            decision = _parse_decision(raw_text)
        except json.JSONDecodeError:
            return {
                "persona_id": persona_id,
                "event": event,
                "error": f"Model/guardrails did not return valid JSON: {raw_text!r}",
                "decision": None,
                "ticket": None,
            }

        result = {
            "persona_id": persona_id,
            "event": event,
            "decision": decision,
            "ticket": None,
        }

        if decision.get("action") == "open_support_ticket":
            ticket_raw = await create_ticket_fn.ainvoke({
                "customer_id": persona["customer_id"],
                "issue_type": decision.get("issue_type") or "general",
                "subject": decision.get("ticket_subject") or "Customer complaint",
                "description": decision.get("ticket_description") or decision.get("reasoning", ""),
            })
            ticket = json.loads(ticket_raw) if isinstance(ticket_raw, str) else ticket_raw
            result["ticket"] = ticket

        memory["trust_score"] = decision.get("trust_score", memory["trust_score"])
        memory["past_decisions"].append({
            "event": event,
            "action": decision.get("action"),
            "trust_score": decision.get("trust_score"),
        })

        return result

    yield FunctionInfo.from_fn(
        _decide_and_act,
        description=(
            "Given a persona_id and an event, decides how that customer "
            "persona reacts and files a real Customer Support ticket if "
            "the decision is to complain."
        ),
    )


# ------------------------------------------------------------------
# Note on memory: resets when the process restarts, same limitation the
# Customer Support system had before SQLite was added. If persona memory
# needs to survive restarts, swap the _memory dict for a small SQLite
# table (persona_id, trust_score, history JSON) without changing the
# calling code above.
# ------------------------------------------------------------------

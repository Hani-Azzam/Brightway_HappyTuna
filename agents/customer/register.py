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
  4. If the decision is to complain_on_social_media or recommend_company,
     publishes a REAL post on the Social Network over its MCP server
     (social_mcp.py), logged in as this persona's display name.

Per-persona memory (trust score, past decisions) is kept in-memory, keyed
by persona_id. See the note at the bottom about upgrading this later.
"""
import json
import logging
import os

from pydantic import Field
from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.rails.llm.config import Instruction

import social_mcp
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


def _install_system_prompt(rails_config: RailsConfig) -> None:
    """
    Puts SYSTEM_PROMPT where NeMo Guardrails actually looks for it.

    The `general` task prompt is composed from the config's `instructions`
    block plus the conversation turns -- a {"role": "system"} message handed to
    generate_async() is silently dropped. Logging the composed prompt showed
    only guardrails_config/config.yml's instructions and the persona JSON: the
    output schema and the action enum never reached the model, which then
    invented its own shape ({"event_response", "emotions", "actions"}) and got
    blocked by the `self check output` rail. Models differ in how close they
    guess, which made this look like a flaky model rather than a missing prompt.

    Nothing else needs the instructions: prompts.yml defines both self_check
    templates in full, so they don't interpolate general_instructions.
    """
    for instruction in rails_config.instructions:
        if instruction.type != "general":
            continue
        if SYSTEM_PROMPT not in instruction.content:
            instruction.content = f"{instruction.content.rstrip()}\n\n{SYSTEM_PROMPT}"
        return
    rails_config.instructions.append(Instruction(type="general", content=SYSTEM_PROMPT))


def _apply_llm_overrides(rails_config: RailsConfig) -> None:
    """
    Lets the root .env repoint the decision model without editing
    guardrails_config/config.yml -- the point being that when NIM's chat
    endpoint is degraded, the whole customer half of the simulation can be
    moved to any OpenAI-compatible endpoint by uncommenting four env vars.
    Unset vars change nothing, so the committed default stays NIM.
    """
    engine = os.environ.get("CUSTOMER_LLM_ENGINE")
    model = os.environ.get("CUSTOMER_LLM_MODEL")
    base_url = os.environ.get("CUSTOMER_LLM_BASE_URL")
    api_key = os.environ.get("CUSTOMER_LLM_API_KEY")
    if not any((engine, model, base_url, api_key)):
        return

    for entry in rails_config.models:
        if entry.type != "main":
            continue
        if engine:
            entry.engine = engine
        if model:
            entry.model = model
        # base_url/api_key ride along in `parameters`, which the framework
        # forwards to the OpenAI-compatible client (see its create_model).
        if base_url or api_key:
            params = dict(entry.parameters or {})
            if base_url:
                params["base_url"] = base_url
            if api_key:
                params["api_key"] = api_key
            entry.parameters = params
        logger.info("LLM override active: engine=%s model=%s base_url=%s",
                    entry.engine, entry.model, base_url or "<default>")


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
    _install_system_prompt(rails_config)
    _apply_llm_overrides(rails_config)
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

        # No {"role": "system"} turn here on purpose -- guardrails drops it.
        # SYSTEM_PROMPT is installed into the config's general instructions
        # instead; see _install_system_prompt above.
        response = await rails.generate_async(messages=[
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
            "post": None,
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

        if decision.get("action") in ("complain_on_social_media", "recommend_company"):
            post_text = decision.get("post_text") or decision.get("reasoning", "")
            try:
                post = await social_mcp.create_post_as(
                    persona_name=persona.get("display_name") or persona_id,
                    content=post_text,
                )
            except Exception as exc:  # noqa: BLE001 -- a failed post must not void the decision
                logger.warning("social post failed for persona=%s: %s", persona_id, exc)
                result["post"] = {"error": str(exc)}
            else:
                result["post"] = post

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

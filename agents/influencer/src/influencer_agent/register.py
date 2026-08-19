"""The NAT workflow itself: one custom function, `influencer_decision`.

By convention, NAT discovers tool/workflow implementations through this module (wired up
via the `nat.components` entry point in pyproject.toml). This function is used directly as
the top-level `workflow` in configs/config.*.yml — it IS the workflow, not a tool called by
some other agent, because the decision this service makes is a single structured LLM call,
not a multi-step tool-calling loop.

It only ever receives a DecisionRequest (persona prompt + one post's text, already resolved
by the poller) and returns a DecisionResult. It never calls social_network and never reads
persona files from disk — see persona.py and poller.py for that.
"""

import json
import logging
import re

from pydantic import Field, ValidationError

from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import LLMRef
from nat.data_models.function import FunctionBaseConfig

from .schemas import DecisionRequest, DecisionResult

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class InfluencerDecisionConfig(FunctionBaseConfig, name="influencer_decision"):
    llm_name: LLMRef = Field(..., description="Name of the LLM (from the `llms:` section) that decides.")
    max_retries: int = Field(default=2, ge=1, description="Attempts to get valid JSON out of the LLM before failing.")


def _extract_json_object(raw_text: str) -> dict:
    """Strips markdown code fences etc. and parses the first JSON object found."""
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.removeprefix("json").strip()

    match = _JSON_OBJECT_RE.search(candidate)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {raw_text!r}")
    return json.loads(match.group(0))


@register_function(config_type=InfluencerDecisionConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def influencer_decision_function(config: InfluencerDecisionConfig, builder: Builder):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    llm = await builder.get_llm(config.llm_name, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

    async def _decide(request: DecisionRequest) -> DecisionResult:
        user_prompt = (
            f'New post by "{request.post_author}":\n"""\n{request.post_content}\n"""\n\n'
            "Respond with the JSON decision now."
        )
        messages: list = [
            SystemMessage(content=request.persona_prompt),
            HumanMessage(content=user_prompt),
        ]

        last_error: Exception | None = None
        for attempt in range(1, config.max_retries + 1):
            response = await llm.ainvoke(messages)
            raw_text = response.content if isinstance(response.content, str) else str(response.content)

            try:
                payload = _extract_json_object(raw_text)
                return DecisionResult.model_validate(payload)
            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("Attempt %d/%d: invalid decision JSON (%s)", attempt, config.max_retries, exc)
                messages.append(AIMessage(content=raw_text))
                messages.append(
                    HumanMessage(
                        content=(
                            f"That response was not valid JSON matching the required schema ({exc}). "
                            "Reply with ONLY the corrected JSON object, no other text."
                        )
                    )
                )

        raise RuntimeError(
            f"LLM failed to produce a valid decision for post {request.post_id!r} "
            f"after {config.max_retries} attempts: {last_error}"
        )

    yield FunctionInfo.from_fn(
        _decide,
        description="Decides whether an influencer persona amplifies, criticizes, or ignores a social_network post.",
        input_schema=DecisionRequest,
    )

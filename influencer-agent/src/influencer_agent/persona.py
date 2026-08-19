"""Loads a persona's system prompt dynamically from two layers:

1. The base template shared by every influencer persona (docs/influencer_persona_prompt.md,
   written in Week 2 — describes the role, objectives, decision process, and constraints).
2. A persona instance file (personas/<name>.yaml) with this specific bot's concrete
   attribute values, bio, and identity.

The base template's own "Output Format" section (action/tone/post/credibility_score/...)
predates this integration and does not match the {decision, reason, responseText} contract
the influencer-agent actually needs. Rather than editing the Week 2 doc, this loader
appends a superseding "Decision Contract" section that is the one the LLM is graded on.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DECISION_CONTRACT = """\
---

# Decision Contract (overrides any earlier "Output Format" example above)

You are being invoked once per new post on the social network. Decide exactly one action:

- "amplify" — you support or want to boost this post to your audience.
- "criticize" — you want to publicly push back on or question this post.
- "ignore" — not worth reacting to; you take no action.

Respond with ONLY a single JSON object, no markdown fences, no commentary, matching exactly:

{
  "decision": "amplify" | "criticize" | "ignore",
  "reason": "short justification grounded in your persona's attributes",
  "responseText": "the comment you would post, in your own voice — omit or null if ignoring"
}

`responseText` is required and must be non-empty for "amplify" and "criticize", and should
read like a real comment (not a summary of your reasoning). Never fabricate facts about
{company_name} beyond what the post itself states.
"""


class PersonaAttributes(BaseModel):
    audience_size: int = Field(..., gt=0)
    influence_level: float = Field(..., ge=0.0, le=1.0)
    credibility: float = Field(..., ge=0.0, le=1.0)
    sensationalism: float = Field(..., ge=0.0, le=1.0)
    controversy_seeking: float = Field(..., ge=0.0, le=1.0)
    brand_support: float = Field(..., ge=0.0, le=1.0)
    viral_probability: float = Field(..., ge=0.0, le=1.0)


class PersonaInstance(BaseModel):
    name: str
    handle: str
    bio: str
    account_type: str = "influencer"
    attributes: PersonaAttributes


def load_persona_instance(persona_file: Path) -> PersonaInstance:
    """Reads a persona instance YAML file (e.g. personas/brand_supporter.yaml)."""
    data = yaml.safe_load(persona_file.read_text(encoding="utf-8"))
    return PersonaInstance.model_validate(data)


def render_persona_prompt(base_template_path: Path, persona: PersonaInstance, company_name: str) -> str:
    """Merges the shared Week 2 base template with this persona's concrete attributes.

    Returns the full system prompt string to send to the LLM for every decision this
    persona makes.
    """
    base_template = base_template_path.read_text(encoding="utf-8")

    attribute_lines = "\n".join(
        f"- {field_name}: {value}" for field_name, value in persona.attributes.model_dump().items()
    )

    persona_section = f"""\
---

# Your Specific Persona: {persona.name} (@{persona.handle})

{persona.bio}

Your attribute values (these are fixed facts about you — stay consistent with them):

{attribute_lines}

The company you are reacting to is {company_name}. You have no information about it beyond
what appears in the post you are shown.
"""

    decision_contract = DECISION_CONTRACT.replace("{company_name}", company_name)

    return f"{base_template}\n\n{persona_section}\n\n{decision_contract}"

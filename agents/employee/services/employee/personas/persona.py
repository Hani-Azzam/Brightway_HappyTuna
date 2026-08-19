"""Persona: the configured identity of one simulated employee.

One agent engine (`agentkit.ToolAgent`) runs many personas. A persona differs by
characteristics, authority, and backstory — never by its tools. This module owns
the schema, the YAML loader, and how a persona renders itself into a system prompt.

The prompt is *data about who the agent is*; the untrusted observations the agent
later reads are kept strictly separate (see domain/perception in a later phase).
"""
from __future__ import annotations

import enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class WhistleblowerTendency(str, enum.Enum):
    never = "never"
    internal_only = "internal_only"
    external_leak = "external_leak"


# Risk Tolerance band → LLM temperature (KB §5.3: lower temperature for safety-relevant
# extraction/policy work, moderate for exploratory reasoning; employees stay conservative).
# Personas set `temperature` explicitly from this band; `test_persona` asserts they agree.
TEMPERATURE_BY_RISK: dict[str, float] = {"low": 0.1, "medium": 0.3, "high": 0.5}


def temperature_for_risk(risk_tolerance: str) -> float:
    return TEMPERATURE_BY_RISK.get((risk_tolerance or "").lower(), 0.1)


class AuthoritySpec(BaseModel):
    # Actions this persona is permitted to take (enforced in code, not just the prompt).
    allowed_actions: list[str] = Field(default_factory=list)
    # Channels it may act through. External channels are gated by whistleblower_tendency.
    channels: list[str] = Field(default_factory=lambda: ["internal_messaging"])


class Persona(BaseModel):
    employee_id: str                      # "EMP-QA-17" — stable key in the registry
    display_name: str
    title: str
    goal: str
    backstory: str = ""
    characteristics: dict[str, str] = Field(default_factory=dict)
    authority: AuthoritySpec = Field(default_factory=AuthoritySpec)
    whistleblower_tendency: WhistleblowerTendency = WhistleblowerTendency.never
    seed: int = 0
    max_steps: int = 6
    temperature: float = 0.1

    def render_system_prompt(self) -> str:
        """Compose the persona identity block injected as the ReAct system hint."""
        chars = "\n".join(f"  - {k.replace('_', ' ')}: {v}"
                          for k, v in self.characteristics.items())
        actions = ", ".join(self.authority.allowed_actions) or "(none)"
        channels = ", ".join(self.authority.channels) or "(none)"
        leak_rule = {
            WhistleblowerTendency.never:
                "You never leak information outside the company.",
            WhistleblowerTendency.internal_only:
                "You may escalate concerns internally, but you never leak outside the company.",
            WhistleblowerTendency.external_leak:
                "Under sufficient provocation you may leak information to external parties.",
        }[self.whistleblower_tendency]

        return (
            f"You are {self.display_name}, a {self.title} at the company "
            f"(agent id: {self.employee_id}).\n"
            f"GOAL: {self.goal}\n"
            f"BACKSTORY: {self.backstory}\n"
            f"YOUR CHARACTER (act consistently with these traits):\n{chars}\n"
            f"AUTHORITY: you may only take these actions: {actions}. "
            f"You act only through these channels: {channels}. "
            f"You CANNOT take actions above your authority (e.g. you cannot stop the factory "
            f"or order a recall — you report and escalate instead). {leak_rule}\n"
            f"Stay in character. Communicate only through the tools you are given."
        )


def load_persona(path: str | Path) -> Persona:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Persona.model_validate(data)


def load_personas(directory: str | Path) -> list[Persona]:
    d = Path(directory)
    return [load_persona(p) for p in sorted(d.glob("*.yaml"))]

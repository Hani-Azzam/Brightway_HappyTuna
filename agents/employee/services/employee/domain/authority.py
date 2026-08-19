"""Authority enforced in code — not just in the prompt.

`Persona.authority` is rendered into the system prompt, but a prompt can be
jail-broken by an injected message. KB §4.1 says authority must be enforced in
code: identity -> permission -> allow/deny -> audit. This module does the
enforceable part for an employee — **channel gating** and the **external-leak
gate** — by wrapping each tool so a forbidden call never executes.

Semantic action types (REPORT_ISSUE vs ESCALATE) depend on message content, so
they remain guided by the prompt; the code guards the channel the tool acts on.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema

from services.employee.personas.persona import Persona, WhistleblowerTendency

# Called on a denial: (tool_name, channel, reason) -> None. Used for audit/memory.
OnDeny = Callable[[str, str, str], None]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


class AuthorityPolicy:
    """Yes/no on a tool call for one persona. A pure function of the persona."""

    def __init__(self, persona: Persona) -> None:
        self._channels = set(persona.authority.channels)
        self._may_leak = (
            persona.whistleblower_tendency == WhistleblowerTendency.external_leak
        )

    def check(self, *, channel: str, is_external: bool) -> Decision:
        if is_external and not self._may_leak:
            return Decision(False, f"external channel '{channel}' forbidden for this persona")
        if channel not in self._channels:
            return Decision(False, f"channel '{channel}' not in allowed channels")
        return Decision(True)


class AuthorizedTool(ToolBase):
    """Wraps a tool with an authority check.

    Presents the SAME schema to the LLM (it doesn't know it's wrapped). On a
    denial the inner tool never runs; the denial comes back as a normal tool
    error the ReAct loop observes, and the audit hook fires.
    """

    def __init__(
        self,
        inner: ToolBase,
        *,
        channel: str,
        policy: AuthorityPolicy,
        is_external: bool = False,
        on_deny: OnDeny | None = None,
    ) -> None:
        self._inner = inner
        self._channel = channel
        self._policy = policy
        self._is_external = is_external
        self._on_deny = on_deny

    @property
    def schema(self) -> ToolSchema:
        return self._inner.schema

    def run(self, **kwargs) -> ToolResult:
        decision = self._policy.check(channel=self._channel, is_external=self._is_external)
        if not decision.allowed:
            if self._on_deny is not None:
                self._on_deny(self._inner.schema.name, self._channel, decision.reason)
            # No side effect happened, so a retry is harmless -> idempotent.
            return ToolResult(error=f"DENIED by authority: {decision.reason}", is_idempotent=True)
        return self._inner.run(**kwargs)


def authorized(
    inner: ToolBase,
    *,
    channel: str,
    policy: AuthorityPolicy,
    is_external: bool = False,
    on_deny: OnDeny | None = None,
) -> AuthorizedTool:
    """Convenience wrapper to register a tool behind the authority check."""
    return AuthorizedTool(
        inner, channel=channel, policy=policy, is_external=is_external, on_deny=on_deny
    )

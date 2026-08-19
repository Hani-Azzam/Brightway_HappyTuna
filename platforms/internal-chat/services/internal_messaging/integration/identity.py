"""Registry: agent_id → role → permissions (KB §4.1 identity/authority chain).

Minimal in-memory implementation. Identity is name-only (matches the social
network and Email); the registry answers "what role is this agent, and may that
role do X". A real deployment swaps this for a shared registry service with no
change to callers.
"""
from __future__ import annotations

from services.internal_messaging.domain.models import default_permissions


class Registry:
    def __init__(self, roles: dict[str, str] | None = None) -> None:
        # agent_id -> role (e.g. "CEO-1" -> "ceo"). Unknown agents default to
        # an "employee"-like role so the sim can run without pre-registration.
        self._roles: dict[str, str] = dict(roles or {})

    def register(self, agent_id: str, role: str) -> None:
        self._roles[agent_id] = role

    def role_of(self, agent_id: str) -> str:
        return self._roles.get(agent_id, "employee")

    def permissions(self, agent_id: str) -> set[str]:
        return default_permissions(self.role_of(agent_id))

    def can(self, agent_id: str, permission: str) -> bool:
        return permission in self.permissions(agent_id)


# The known world roster (sim scale). A real deployment loads this from a shared
# registry service; here it seeds the in-memory one so leadership gets its role and
# — crucially — the activation layer (`COORD-1`) gets `chat:system` while no agent
# does. Unlisted agents still resolve to a read/write "employee" (see `role_of`).
_DEFAULT_ROSTER: dict[str, str] = {
    "CEO-1": "ceo",
    "EMP-QA-17": "employee",
    "PROD-WORKER-3": "employee",
    "PLANT-MGR-1": "employee",
    "CONCERNED-EMP-1": "employee",
    "WHISTLEBLOWER-1": "employee",
    "COORD-1": "coordinator",
}


def default_registry() -> Registry:
    return Registry(dict(_DEFAULT_ROSTER))

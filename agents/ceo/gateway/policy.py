"""Filters the catalog down to what one role may see and call.

Three rules, in order: deny wins (exact names only), an allow match grants,
anything else is denied. Default-deny is what makes the surface closed: a tool
that appears on a server tomorrow is invisible until somebody decides otherwise.

SHARP EDGE: a whole-server allow ("analytics.*") is a namespace grant, not a read
grant -- it sweeps in that server's writes too. Today it takes run_analysis and
set_ai_analysis, which mutate the numbers the CEO is scored against; "support.*"
takes create_ticket, which fabricates a customer complaint. The explicit deny
entries in roles.yaml are therefore load-bearing, not belt-and-braces: deleting
one silently hands the agent operator-level powers. Anything added upstream to a
wildcarded server is granted the moment it appears, with no review.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .catalog import Catalog
from .models import PolicyDecision, RoleConfig, ToolEntry

logger = logging.getLogger(__name__)

#: Points at an alternative roles file. Handy for tests; not needed normally.
ROLES_PATH_ENV_VAR = "GATEWAY_ROLES_PATH"

#: ceo_agent/roles.yaml -- one level up from this package.
DEFAULT_ROLES_PATH = Path(__file__).resolve().parents[1] / "roles.yaml"

#: Suffix marking a whole-server allow entry, e.g. "analytics.*".
SERVER_WILDCARD_SUFFIX = ".*"


class PolicyError(RuntimeError):
    """The roles file is missing, malformed, or violates the matching rules.

    Raised rather than warned. A policy that cannot be parsed exactly as written
    is not a policy, and quietly falling back to a default would hand the agent a
    surface nobody authored.
    """


class _RolesFile(BaseModel):
    """The whole roles file."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    roles: dict[str, Any] = Field(min_length=1)


def _validate_pattern(pattern: str, *, role_id: str, field: str, allow_wildcards: bool) -> None:
    """Rejects anything outside the two supported forms.

    Supported: "server.tool" (exact) and, for allow only, "server.*" (whole
    server). Everything else -- bare "*", "*.search", partial globs like
    "social.get_*" -- is refused.

    The restriction is deliberate. A partial glob reads as if it enumerates a
    known set, but it silently absorbs whatever a team adds next: "social.get_*"
    would grant a future `get_private_messages` without anyone deciding to. Exact
    names and whole-server grants are both auditable at a glance; the middle
    ground is not. Relaxing this later is a small change, and the loud failure
    here is what forces that to be a decision rather than an accident.
    """
    if not pattern or pattern.strip() != pattern:
        raise PolicyError(
            f"Role {role_id!r} has an empty or padded {field} entry: {pattern!r}."
        )

    if "*" in pattern:
        if not allow_wildcards:
            raise PolicyError(
                f"Role {role_id!r} has a wildcard in its deny list: {pattern!r}. "
                f"Deny entries must be exact 'server.tool' names. Three tool names "
                f"(search, get_post, get_hashtag_posts) exist on two servers each, so a "
                f"pattern deny can revoke the wrong server's tool -- or match nothing at "
                f"all while looking like it worked."
            )
        if not pattern.endswith(SERVER_WILDCARD_SUFFIX) or pattern.count("*") != 1:
            raise PolicyError(
                f"Role {role_id!r} has an unsupported wildcard in {field}: {pattern!r}. "
                f"The only supported wildcard is a whole server, written 'server.*'. "
                f"Partial globs are refused because they silently absorb tools that do "
                f"not exist yet."
            )

    server_part, _, tool_part = pattern.partition(".")
    if not server_part or not tool_part:
        raise PolicyError(
            f"Role {role_id!r} has a malformed {field} entry: {pattern!r}. "
            f"Expected 'server.tool' or 'server.*'."
        )
    if "." in tool_part:
        raise PolicyError(
            f"Role {role_id!r} has a malformed {field} entry: {pattern!r}. "
            f"Expected exactly one '.' separating server from tool."
        )


def load_roles(path: Path | str | None = None) -> dict[str, RoleConfig]:
    """Reads roles.yaml and returns the validated roles, keyed by id.

    Raises `PolicyError` if the file is missing or malformed, or if any entry
    breaks the matching rules (a wildcard in deny, a partial glob anywhere).
    """
    if path is not None:
        roles_path = Path(path)
    else:
        from_env = os.environ.get(ROLES_PATH_ENV_VAR, "").strip()
        roles_path = Path(from_env) if from_env else DEFAULT_ROLES_PATH

    try:
        raw_text = roles_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyError(f"Roles file not found: {roles_path}") from exc
    except OSError as exc:
        raise PolicyError(f"Could not read roles file {roles_path}: {exc}") from exc

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise PolicyError(f"Roles file {roles_path} is not valid YAML: {exc}") from exc

    if not isinstance(parsed, dict):
        raise PolicyError(
            f"Roles file {roles_path} must contain a YAML mapping at the top level."
        )

    try:
        roles_file = _RolesFile.model_validate(parsed)
    except ValidationError as exc:
        raise PolicyError(f"Roles file {roles_path} is invalid:\n{exc}") from exc

    roles: dict[str, RoleConfig] = {}
    for role_id, body in roles_file.roles.items():
        if not isinstance(body, dict):
            raise PolicyError(
                f"Role {role_id!r} in {roles_path} must be a mapping with allow/deny keys."
            )
        try:
            role = RoleConfig(id=role_id, **body)
        except ValidationError as exc:
            raise PolicyError(f"Role {role_id!r} in {roles_path} is invalid:\n{exc}") from exc

        for pattern in role.allow:
            _validate_pattern(pattern, role_id=role_id, field="allow", allow_wildcards=True)
        for pattern in role.deny:
            _validate_pattern(pattern, role_id=role_id, field="deny", allow_wildcards=False)

        roles[role_id] = role

    logger.info(
        "Loaded %d role(s) from %s: %s", len(roles), roles_path, ", ".join(sorted(roles))
    )
    return roles


def get_role(role_id: str, path: Path | str | None = None) -> RoleConfig:
    """Loads one role by id, raising `PolicyError` if it is not defined."""
    roles = load_roles(path)
    role = roles.get(role_id)
    if role is None:
        raise PolicyError(
            f"No role {role_id!r} defined. Available roles: {', '.join(sorted(roles)) or 'none'}."
        )
    return role


class Policy:
    """One role's filter over the catalog.

    Stateless with respect to the catalog: `decide` answers for any qualified
    name, whether or not it exists, so `router.py` can check an inbound call
    before looking anything up.
    """

    def __init__(self, role: RoleConfig) -> None:
        self.role = role
        # Exact denies only, so membership is the whole deny check.
        self._deny: set[str] = set(role.deny)
        self._allow_exact: set[str] = {p for p in role.allow if not p.endswith(SERVER_WILDCARD_SUFFIX)}
        self._allow_servers: set[str] = {
            p[: -len(SERVER_WILDCARD_SUFFIX)] for p in role.allow if p.endswith(SERVER_WILDCARD_SUFFIX)
        }

    @property
    def role_id(self) -> str:
        return self.role.id

    def decide(self, qualified_name: str) -> PolicyDecision:
        """Resolves one qualified name to a verdict plus the rule that produced it."""
        if qualified_name in self._deny:
            return PolicyDecision(
                qualified_name=qualified_name,
                allowed=False,
                reason="explicit_deny",
                matched_rule=qualified_name,
            )

        # An exact allow beats a server wildcard only in reporting; both grant.
        if qualified_name in self._allow_exact:
            return PolicyDecision(
                qualified_name=qualified_name,
                allowed=True,
                reason="allow_match",
                matched_rule=qualified_name,
            )

        server_id, _, tool_name = qualified_name.partition(".")
        if tool_name and server_id in self._allow_servers:
            return PolicyDecision(
                qualified_name=qualified_name,
                allowed=True,
                reason="allow_match",
                matched_rule=f"{server_id}{SERVER_WILDCARD_SUFFIX}",
            )

        return PolicyDecision(
            qualified_name=qualified_name,
            allowed=False,
            reason="default_deny",
            matched_rule=None,
        )

    def is_allowed(self, qualified_name: str) -> bool:
        """True when the role may call this tool."""
        return self.decide(qualified_name).allowed

    def visible_tools(self, catalog: Catalog) -> list[ToolEntry]:
        """The catalog entries this role may see, in catalog order."""
        return [entry for entry in catalog if self.is_allowed(entry.qualified_name)]

    def decisions(self, catalog: Catalog) -> list[PolicyDecision]:
        """A verdict for every tool in the catalog, in catalog order."""
        return [self.decide(entry.qualified_name) for entry in catalog]

    def validate_against_catalog(self, catalog: Catalog) -> list[str]:
        """Reports rules that match nothing in the live catalog.

        Returned rather than raised. Under default-deny both kinds of dead rule
        are fail-safe: an allow that matches nothing grants nothing, and a deny
        that matches nothing revokes nothing that exists -- and if the tool it
        named was renamed, the new name is not in the allow list either, so it
        stays hidden. Neither can open a hole, so neither should stop a run.

        They are still worth surfacing: a dead rule usually means a tool was
        renamed upstream, or that someone wrote a name that was never right.
        """
        problems: list[str] = []
        known_names = {entry.qualified_name for entry in catalog}
        known_servers = set(catalog.server_ids)

        for pattern in self.role.allow:
            if pattern.endswith(SERVER_WILDCARD_SUFFIX):
                server_id = pattern[: -len(SERVER_WILDCARD_SUFFIX)]
                if server_id not in known_servers:
                    problems.append(
                        f"allow {pattern!r} matches no connected server "
                        f"(connected: {', '.join(sorted(known_servers)) or 'none'})"
                    )
            elif pattern not in known_names:
                server_id = pattern.partition(".")[0]
                elsewhere = sorted(
                    n for n in known_names if n.partition(".")[2] == pattern.partition(".")[2]
                )
                hint = f" -- did you mean {', '.join(elsewhere)}?" if elsewhere else ""
                problems.append(f"allow {pattern!r} matches no tool in the catalog{hint}")

        for pattern in self.role.deny:
            if pattern not in known_names:
                problems.append(
                    f"deny {pattern!r} matches no tool in the catalog -- it revokes nothing"
                )

        return problems


def build_policy(role_id: str, path: Path | str | None = None) -> Policy:
    """Loads a role and returns its `Policy`. The usual entry point."""
    return Policy(get_role(role_id, path))

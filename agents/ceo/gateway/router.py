"""The only gateway surface the CEO agent ever touches.

`call_tool` runs policy, identity injection, the dry-run gate, audit, then
dispatch. The policy check happens here and not only in `get_tools` on purpose:
filtering the advertised list is presentation, this is enforcement. A model that
hallucinates a tool name, or recalls one from an earlier turn under a different
role, is stopped by the same check that built the list.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from langchain_core.tools import StructuredTool

from .catalog import Catalog
from .connection import GatewayConnections
from .connection import call_tool as dispatch_tool
from .models import PolicyDecision, ServerStatus, ToolEntry, ToolResult
from .policy import Policy, build_policy

logger = logging.getLogger(__name__)

#: LangChain rejects "." in tool names, so qualified names are re-spelled with
#: this separator on the way out and resolved back on the way in.
LANGCHAIN_SEPARATOR = "__"

DEFAULT_AUDIT_PATH = Path(__file__).resolve().parents[1] / "logs" / "gateway_audit.jsonl"

INJECTED_PARAMS: dict[str, set[str]] = {
    # Their MCP layer defaults actor to "system" when omitted
    # (Customer_Support_System/mcp_server.py:145), which would file the CEO's
    # crisis decisions under nobody. The gateway always supplies it, and
    # prepare_schema strips it so the model can neither forge nor forget it.
    "support.patch_ticket": {"actor"},
}

# Transcribed from Customer_Support_System/models.py:7-34. Their MCP layer types
# these parameters as bare `str` and documents the legal values only in docstring
# prose, so the advertised schema carries no constraint and a model can emit
# "contamination" for issue_type -- a server-side ValueError from
# IssueType(issue_type) (mcp_server.py:67) it had no way to avoid.
#
# DRIFT: hand-maintained copy. If their team adds a member, this silently lags;
# there is no import that would fail. Re-read that file when it changes.
TICKET_STATUS_VALUES = ["open", "in_progress", "escalated", "resolved", "closed"]
TICKET_PRIORITY_VALUES = ["low", "medium", "high", "critical"]
ISSUE_TYPE_VALUES = ["quality", "delivery", "billing", "general", "safety_concern"]

# Sentiment is deliberately absent: it is not an input on any tool, but scored
# from the description text ("do not pass sentiment yourself", mcp_server.py:44).
ENUM_INJECTIONS: dict[str, dict[str, list[str]]] = {
    "support.create_ticket": {
        "issue_type": ISSUE_TYPE_VALUES,
        "priority": TICKET_PRIORITY_VALUES,
    },
    "support.patch_ticket": {
        "status": TICKET_STATUS_VALUES,
        "priority": TICKET_PRIORITY_VALUES,
    },
}


def _apply_enum(prop_schema: dict[str, Any], values: list[str]) -> bool:
    """Constrains one property to `values`, returning whether anything changed.

    Optional parameters arrive as `{"anyOf": [{"type": "string"}, {"type": "null"}],
    "default": null}`. The constraint goes on the string branch only -- hoisting it
    to the top level would make the property's own default of `null` illegal.
    """
    branches = prop_schema.get("anyOf")
    if isinstance(branches, list):
        applied = False
        for branch in branches:
            if isinstance(branch, dict) and branch.get("type") == "string":
                branch["enum"] = list(values)
                applied = True
        return applied

    if prop_schema.get("type") == "string":
        prop_schema["enum"] = list(values)
        return True

    return False


def prepare_schema(entry: ToolEntry) -> dict[str, Any]:
    """The input schema as the model should see it.

    Strips gateway-injected parameters and adds the enum constraints the upstream
    servers left off. Everything else is passed through untouched.
    """
    schema = deepcopy(entry.input_schema)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return schema

    for param in INJECTED_PARAMS.get(entry.qualified_name, set()):
        properties.pop(param, None)
        required = schema.get("required")
        if isinstance(required, list) and param in required:
            schema["required"] = [r for r in required if r != param]

    for param, values in ENUM_INJECTIONS.get(entry.qualified_name, {}).items():
        prop = properties.get(param)
        if not isinstance(prop, dict):
            logger.warning(
                "Enum injection skipped: %s has no %r parameter any more. "
                "ENUM_INJECTIONS in gateway/router.py is out of date.",
                entry.qualified_name,
                param,
            )
            continue
        if not _apply_enum(prop, values):
            logger.warning(
                "Enum injection skipped: %s.%s is not a string-typed property.",
                entry.qualified_name,
                param,
            )

    return schema


def to_langchain_name(qualified_name: str) -> str:
    """Re-spells a qualified name for LangChain, which rejects dots.

    The reverse map is built by applying this function across the catalog rather
    than by string surgery, so the two directions cannot disagree.
    """
    return qualified_name.replace(".", LANGCHAIN_SEPARATOR)


class AuditLog:
    """Append-only JSONL record of every call the agent attempts.

    Two lines per call sharing a `call_id`, not one rewritten line: an audit trail
    that edits its own history is not evidence, and a start with no matching end is
    exactly how a crash or a hang shows up. Calls that never dispatch (denied,
    unknown, dry-run) write both lines too, so the log answers "what did the agent
    try to do", not merely "what did it succeed at".
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_AUDIT_PATH

    def _write(self, record: dict[str, Any]) -> None:
        try:
            # On first write, not on construction: building a Router to inspect a
            # tool surface must not leave an empty logs/ directory behind.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
        except OSError as exc:
            # Must not take down a simulation run, must not pass unnoticed either.
            logger.error("Could not write audit record to %s: %s", self.path, exc)

    def start(self, *, call_id: str, role: str, qualified_name: str, access: str | None,
              args: dict[str, Any]) -> None:
        self._write({
            "event": "call_start",
            "call_id": call_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "qualified_name": qualified_name,
            "access": access,
            "args": args,
        })

    def end(self, *, call_id: str, role: str, result: ToolResult, access: str | None,
            args: dict[str, Any], outcome: str) -> None:
        self._write({
            "event": "call_end",
            "call_id": call_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "qualified_name": result.qualified_name,
            "access": access,
            "args": args,
            "outcome": outcome,
            "ok": result.ok,
            "is_error": result.is_error,
            "error": result.error,
            "elapsed_ms": round(result.elapsed_ms, 2),
        })


class Router:
    """The agent-facing gateway.

    Bound to one role at construction. The role arguments on the getters are for
    inspection; `call_tool` always enforces the bound role, so what the agent is
    shown and what it may run cannot come apart.
    """

    def __init__(
        self,
        connections: GatewayConnections,
        catalog: Catalog,
        role: str,
        *,
        dry_run: bool = False,
        audit_path: Path | str | None = None,
        actor: str | None = None,
    ) -> None:
        self._connections = connections
        self._catalog = catalog
        self._role_id = role
        self._policy: Policy = build_policy(role)
        self._dry_run = dry_run
        self._audit = AuditLog(audit_path)
        #: Written into injected identity parameters. The role id is what then
        #: shows up in the support activity log instead of "system".
        self._actor = actor or role
        #: Derived from to_langchain_name so the two directions cannot drift.
        self._from_langchain: dict[str, str] = {
            to_langchain_name(e.qualified_name): e.qualified_name for e in catalog
        }

        if dry_run:
            logger.warning(
                "Router is in DRY RUN: every write is answered without reaching the "
                "server -- public_write and write alike. Reads still execute normally, "
                "so the agent sees real data and changes nothing."
            )

    @property
    def role_id(self) -> str:
        return self._role_id

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def get_status(self) -> list[ServerStatus]:
        """Connection state per configured server, including skipped ones.

        A CEO who stayed silent and a CEO who could not reach the platform must not
        look the same in the transcript.
        """
        return self._connections.statuses

    def _policy_for(self, role: str | None) -> Policy:
        if role is None or role == self._role_id:
            return self._policy
        logger.warning(
            "Router is bound to role %r; listing tools for %r is inspection only -- "
            "call_tool still enforces %r.",
            self._role_id,
            role,
            self._role_id,
        )
        return build_policy(role)

    def get_tools(self, role: str | None = None) -> list[ToolEntry]:
        """The catalog entries this role may use, schemas unmodified."""
        return self._policy_for(role).visible_tools(self._catalog)

    def get_tools_for_llm(self, role: str | None = None) -> list[dict[str, Any]]:
        """The tool list as a model should receive it: prepared schemas, dotted names."""
        return [
            {
                "name": entry.qualified_name,
                "description": entry.description or entry.title or entry.tool_name,
                "input_schema": prepare_schema(entry),
            }
            for entry in self.get_tools(role)
        ]

    def get_langchain_tools(self, role: str | None = None) -> list[StructuredTool]:
        """The same tools as LangChain `StructuredTool`s wrapping `call_tool`.

        Built from `get_tools_for_llm`, so the schema a LangGraph agent binds is
        byte-for-byte the one any other caller sees. `args_schema` takes the
        prepared JSON schema directly -- no parallel pydantic model to fall out of
        sync.
        """
        tools: list[StructuredTool] = []

        for spec in self.get_tools_for_llm(role):
            qualified_name = spec["name"]
            tools.append(
                StructuredTool.from_function(
                    coroutine=self._make_coroutine(qualified_name),
                    name=to_langchain_name(qualified_name),
                    description=spec["description"],
                    args_schema=spec["input_schema"],
                )
            )
        return tools

    def _make_coroutine(self, qualified_name: str) -> Callable[..., Any]:
        async def _invoke(**kwargs: Any) -> Any:
            result = await self.call_tool(qualified_name, kwargs)
            # The tool's own JSON, so the model sees no wrapper it has to learn.
            if result.ok:
                return result.data if result.data is not None else (result.text or "")
            return f"Error: {result.error}"

        return _invoke

    def _resolve_name(self, name: str) -> str:
        """Accepts either spelling of a tool name and returns the qualified one."""
        if name in self._from_langchain:
            return self._from_langchain[name]
        return name

    def _failed(self, qualified_name: str, error: str, started: float) -> ToolResult:
        server_id, _, tool_name = qualified_name.partition(".")
        return ToolResult(
            qualified_name=qualified_name,
            server_id=server_id,
            tool_name=tool_name or qualified_name,
            ok=False,
            error=error,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    async def call_tool(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """Runs one tool call through policy, identity, dry-run, audit, dispatch.

        Never raises. A denied name, an unknown name, and a server error all come
        back as `ToolResult(ok=False)` with a readable `error`, so a model that
        hallucinated a tool can read what went wrong instead of crashing the run.
        """
        started = time.perf_counter()
        qualified_name = self._resolve_name(name)
        args = dict(args or {})
        call_id = uuid.uuid4().hex[:12]
        entry = self._catalog.get(qualified_name)
        access = entry.access if entry else None

        unknown_error = (
            f"No such tool {qualified_name!r}. Call one of the tools you were "
            f"given; names are '<server>.<tool>'."
        )

        decision: PolicyDecision = self._policy.decide(qualified_name)
        if not decision.allowed:
            error = unknown_error if entry is None else (
                f"Tool {qualified_name!r} is not available to role "
                f"{self._role_id!r} ({decision.reason})."
            )
            result = self._failed(qualified_name, error, started)
            self._audit.start(call_id=call_id, role=self._role_id,
                              qualified_name=qualified_name, access=access, args=args)
            self._audit.end(call_id=call_id, role=self._role_id, result=result,
                            access=access, args=args, outcome="denied")
            logger.warning("Denied %s for role %r: %s", qualified_name, self._role_id, decision.reason)
            return result

        # Allowed, but no such tool: a server wildcard ("support.*") grants any name
        # on that server, including ones the catalog has never seen. Without this the
        # call reaches dispatch and reports "server is not connected", which is false
        # and sends the reader debugging the wrong layer.
        if entry is None:
            result = self._failed(qualified_name, unknown_error, started)
            self._audit.start(call_id=call_id, role=self._role_id,
                              qualified_name=qualified_name, access=access, args=args)
            self._audit.end(call_id=call_id, role=self._role_id, result=result,
                            access=access, args=args, outcome="unknown_tool")
            logger.warning("Unknown tool %s requested by role %r", qualified_name, self._role_id)
            return result

        # Overwrites rather than defaults: the parameter is stripped from the
        # advertised schema, so anything already here came from a caller that
        # should not have been setting it.
        for param in INJECTED_PARAMS.get(qualified_name, set()):
            args[param] = self._actor

        # Every write is held back, tested as "not a read" rather than by listing
        # the write levels. A level added to AccessLevel later is then withheld by
        # default and someone has to decide to let it through, which is the same
        # fail-safe direction as policy.py's default-deny.
        #
        # This used to gate `access == "public_write"`, on the reasoning that only
        # the irreversible public actions were worth stopping. That made the flag
        # narrower than its name: a dry run still patched real tickets, and once
        # chat arrived it could open channels on a server with no delete_channel
        # and no remove_member -- a permanent side effect from a run whose whole
        # promise is that it has none. "Dry run" has to mean nothing is written.
        if self._dry_run and access != "read":
            result = ToolResult(
                qualified_name=qualified_name,
                server_id=entry.server_id,
                tool_name=entry.tool_name,
                ok=True,
                data={"dry_run": True, "would_send": args},
                text=None,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
            self._audit.start(call_id=call_id, role=self._role_id,
                              qualified_name=qualified_name, access=access, args=args)
            self._audit.end(call_id=call_id, role=self._role_id, result=result,
                            access=access, args=args, outcome="dry_run")
            logger.info("DRY RUN %s -- not sent: %s", qualified_name, args)
            return result

        # Audited before it can have any effect.
        self._audit.start(call_id=call_id, role=self._role_id,
                          qualified_name=qualified_name, access=access, args=args)

        session = self._connections.session_for(entry.server_id)
        config = self._connections.config_for(entry.server_id)
        if session is None or config is None:
            result = self._failed(
                qualified_name,
                f"Server {entry.server_id!r} is not connected. It was skipped at "
                f"startup -- see get_status() for why.",
                started,
            )
            self._audit.end(call_id=call_id, role=self._role_id, result=result,
                            access=access, args=args, outcome="unavailable")
            return result

        result = await dispatch_tool(session, config, entry.tool_name, args)
        self._audit.end(call_id=call_id, role=self._role_id, result=result,
                        access=access, args=args,
                        outcome="ok" if result.ok else "error")
        return result

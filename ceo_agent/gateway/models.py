"""Pydantic models shared by every layer. Pure data -- no I/O, no MCP imports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Which set of hostnames to read out of mcp_servers.yaml.
#:   docker -- compose service names, for running inside the compose network
#:   local  -- host-published ports, for running the gateway off-compose
Profile = Literal["docker", "local"]

#: What calling a tool does to the world.
#:
#:   read         -- observes only.
#:   write        -- changes state inside the company's own systems. Recoverable
#:                   or invisible to the public.
#:   public_write -- publishes into the simulated world irreversibly. No server
#:                   exposes an undo tool for these.
#:
#: Assigned only from the explicit table in `catalog.py`, never inferred from a
#: tool's name.
AccessLevel = Literal["read", "write", "public_write"]


class LoginSpec(BaseModel):
    """A single login call, run once per session before any other tool.

    Only the social server needs one: its identity lives in per-session closure
    state (`socialServer.ts:38`), and every write tool throws 401 until `login`
    populates it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class SetupStep(BaseModel):
    """One post-login call.

    Must be idempotent: these are replayed verbatim on every reconnect, since a
    restarted server hands back a brand-new, empty session.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class ServerConfig(BaseModel):
    """One MCP server, with its URL already resolved for the active profile.

    `registry.py` picks `url` out of the `urls: {docker, local}` map in
    mcp_servers.yaml, so profile handling never leaks past the registry and this
    model stays a flat, final description of one connection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Becomes the catalog namespace prefix ("support" -> "support.create_ticket"),
    # so it must not contain a dot or `qualified_name` would be ambiguous to split.
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    url: str
    enabled: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0)
    login: LoginSpec | None = None
    post_login_setup: list[SetupStep] = Field(default_factory=list)


class ToolEntry(BaseModel):
    """One tool from one server, as it appears in the namespaced catalog.

    `server_id` and `tool_name` are their own fields rather than re-parsed out of
    `qualified_name`, so routing never depends on string splitting.
    """

    model_config = ConfigDict(extra="forbid")

    qualified_name: str  # "support.create_ticket"
    server_id: str  # "support"
    tool_name: str  # "create_ticket" -- the name that goes on the wire
    # Required, with no default: a tool whose blast radius nobody has decided on
    # must fail the catalog build, never quietly arrive as the safest-looking value.
    access: AccessLevel
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """The outcome of one tool call. Never raised -- always returned.

    `ok` and `is_error` are separate on purpose: `is_error` is what the server
    reported, while `ok` is also False for a timeout or a dropped connection,
    where the server reported nothing at all. Callers check `ok`.

    `data` is the JSON payload exactly as sent, unwrapped -- the three servers
    disagree on shape and normalising that is not this layer's decision.
    """

    model_config = ConfigDict(extra="forbid")

    qualified_name: str
    server_id: str
    tool_name: str
    ok: bool
    is_error: bool = False
    text: str | None = None
    data: Any | None = None
    error: str | None = None
    elapsed_ms: float = 0.0


class RoleConfig(BaseModel):
    """One role's view of the catalog, as declared in roles.yaml.

    `deny` always wins; a tool matching neither list is denied.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str | None = None
    allow: list[str] = Field(default_factory=list)
    # Exact qualified names only -- never wildcards. `search`, `get_post`, and
    # `get_hashtag_posts` each exist on two servers, so a pattern deny is one
    # typo away from revoking the wrong server's tool, or from looking like it
    # revoked something it never matched.
    deny: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    """Why one tool is or is not visible to a role.

    Carries the deciding rule, not just the verdict, so a surprising surface can
    be traced to the line of roles.yaml that produced it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    qualified_name: str
    allowed: bool
    #: explicit_deny -- matched a deny entry (deny always wins)
    #: allow_match   -- matched an allow entry and no deny entry
    #: default_deny  -- matched nothing at all; closed by default
    reason: Literal["explicit_deny", "allow_match", "default_deny"]
    matched_rule: str | None = None


class ServerStatus(BaseModel):
    """What happened when the gateway tried to bring one server up.

    Exists so degradation is legible rather than silent: if social is down for a
    round, "the CEO made no public statement" and "the CEO could not reach the
    platform" otherwise produce identical transcripts.

    `login_ok` and `setup_ok` are None when nothing is configured, distinguishing
    "not applicable" from "ran and failed".
    """

    model_config = ConfigDict(extra="forbid")

    server_id: str
    enabled: bool
    connected: bool = False
    skipped_reason: str | None = None
    login_attempted: bool = False
    login_ok: bool | None = None
    # The token the login tool returned. For social this is the CEO's own user id
    # (`authService.ts:26` returns `{ token: user.id, user }`), which later layers
    # need to read back the agent's own posts.
    identity: str | None = None
    setup_attempted: bool = False
    setup_ok: bool | None = None
    setup_errors: list[str] = Field(default_factory=list)
    tool_count: int | None = None
    error: str | None = None

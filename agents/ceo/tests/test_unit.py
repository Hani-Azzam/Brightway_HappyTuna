"""Unit tests. No network, no Docker, no MCP servers.

    pytest ceo_agent/tests/test_unit.py

Everything here runs against temp config files and fake sessions. If any test in
this file needs a server to be up, it is in the wrong file.
"""

from __future__ import annotations

import copy
import logging

import pytest
from mcp.types import ListToolsResult, Tool

from gateway.catalog import CatalogError, TOOL_ACCESS, build_catalog, qualify
from gateway.models import ToolEntry
from gateway.policy import PolicyError, build_policy, load_roles
from gateway.registry import RegistryError, load_registry
from gateway.router import Router, prepare_schema, to_langchain_name

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSession:
    """Just enough ClientSession to build a catalog: one page of tools."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = tools

    async def list_tools(self, params=None) -> ListToolsResult:
        return ListToolsResult(tools=self._tools, nextCursor=None)


def tool(name: str, schema: dict | None = None) -> Tool:
    return Tool(
        name=name,
        description=f"{name} description",
        inputSchema=schema or {"type": "object", "properties": {}},
    )


def write_registry(tmp_path, body: str):
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def write_roles(tmp_path, body: str):
    path = tmp_path / "roles.yaml"
    path.write_text(body, encoding="utf-8")
    return path


TWO_SERVER_REGISTRY = """
version: 1
default_profile: docker
servers:
  - id: support
    urls:
      docker: http://customer-support-mcp:8010/mcp
      local: http://localhost:8010/mcp
  - id: social
    timeout_seconds: 15.0
    urls:
      docker: http://social-network:3000/mcp/social
      local: http://localhost:3005/mcp/social
"""


# ---------------------------------------------------------------------------
# registry: parsing and profile resolution
# ---------------------------------------------------------------------------


def test_registry_parses_and_resolves_explicit_profile(tmp_path):
    path = write_registry(tmp_path, TWO_SERVER_REGISTRY)

    configs = load_registry(path, profile="local")

    assert [c.id for c in configs] == ["support", "social"]
    assert configs[0].url == "http://localhost:8010/mcp"
    assert configs[1].url == "http://localhost:3005/mcp/social"
    # Defaults applied, and per-server overrides respected.
    assert configs[0].timeout_seconds == 30.0
    assert configs[1].timeout_seconds == 15.0
    assert all(c.enabled for c in configs)


def test_profile_precedence_explicit_over_env_over_file(tmp_path, monkeypatch):
    path = write_registry(tmp_path, TWO_SERVER_REGISTRY)

    # 1. File's default_profile, with nothing else set.
    monkeypatch.delenv("GATEWAY_URL_PROFILE", raising=False)
    assert load_registry(path)[0].url.startswith("http://customer-support-mcp")

    # 2. Env var beats the file.
    monkeypatch.setenv("GATEWAY_URL_PROFILE", "local")
    assert load_registry(path)[0].url.startswith("http://localhost")

    # 3. Explicit argument beats the env var.
    assert load_registry(path, profile="docker")[0].url.startswith("http://customer-support-mcp")


def test_registry_path_env_var_is_honoured(tmp_path, monkeypatch):
    path = write_registry(tmp_path, TWO_SERVER_REGISTRY)
    monkeypatch.setenv("GATEWAY_REGISTRY_PATH", str(path))
    monkeypatch.delenv("GATEWAY_URL_PROFILE", raising=False)

    assert len(load_registry()) == 2


def test_disabled_server_is_returned_not_dropped(tmp_path):
    path = write_registry(tmp_path, """
version: 1
servers:
  - id: support
    enabled: false
    urls: {docker: http://x/mcp}
""")

    configs = load_registry(path, profile="docker")

    # connection.py must be able to name it in a WARNING, so it survives here.
    assert len(configs) == 1
    assert configs[0].enabled is False


def test_duplicate_server_id_raises(tmp_path):
    path = write_registry(tmp_path, """
version: 1
servers:
  - id: support
    urls: {docker: http://a/mcp}
  - id: support
    urls: {docker: http://b/mcp}
""")

    with pytest.raises(RegistryError, match="Duplicate server id"):
        load_registry(path, profile="docker")


def test_missing_url_for_active_profile_raises(tmp_path):
    path = write_registry(tmp_path, TWO_SERVER_REGISTRY)

    with pytest.raises(RegistryError, match="no URL for profile 'staging'"):
        load_registry(path, profile="staging")


def test_unknown_key_raises(tmp_path):
    path = write_registry(tmp_path, """
version: 1
servers:
  - id: support
    urls: {docker: http://a/mcp}
    retries: 3
""")

    with pytest.raises(RegistryError):
        load_registry(path, profile="docker")


def test_missing_file_raises(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "nope.yaml")


# ---------------------------------------------------------------------------
# policy: precedence
# ---------------------------------------------------------------------------


ROLES = """
version: 1
roles:
  ceo:
    allow:
      - "analytics.*"
      - "social.create_post"
    deny:
      - "analytics.run_analysis"
"""


@pytest.fixture()
def policy(tmp_path):
    return build_policy("ceo", write_roles(tmp_path, ROLES))


def test_deny_beats_server_wildcard_allow(policy):
    decision = policy.decide("analytics.run_analysis")

    assert decision.allowed is False
    assert decision.reason == "explicit_deny"
    assert decision.matched_rule == "analytics.run_analysis"


def test_server_wildcard_allows_the_rest_of_that_server(policy):
    decision = policy.decide("analytics.get_overview")

    assert decision.allowed is True
    assert decision.reason == "allow_match"
    assert decision.matched_rule == "analytics.*"


def test_exact_allow_grants(policy):
    decision = policy.decide("social.create_post")

    assert decision.allowed is True
    assert decision.matched_rule == "social.create_post"


def test_unlisted_tool_on_allowed_server_family_is_default_denied(policy):
    # social has no wildcard, so a sibling tool is not granted.
    decision = policy.decide("social.login")

    assert decision.allowed is False
    assert decision.reason == "default_deny"
    assert decision.matched_rule is None


def test_unknown_name_is_denied(policy):
    # A hallucinated name resolves without touching the catalog.
    for name in ("support.delete_everything", "not_a_server.tool", "gibberish"):
        decision = policy.decide(name)
        assert decision.allowed is False, name
        assert decision.reason == "default_deny", name


def test_wildcard_in_deny_is_rejected_at_load_time(tmp_path):
    path = write_roles(tmp_path, """
version: 1
roles:
  ceo:
    allow: ["analytics.*"]
    deny: ["analytics.*"]
""")

    with pytest.raises(PolicyError, match="wildcard in its deny list"):
        load_roles(path)


def test_partial_glob_is_rejected(tmp_path):
    path = write_roles(tmp_path, """
version: 1
roles:
  ceo:
    allow: ["social.get_*"]
""")

    with pytest.raises(PolicyError, match="unsupported wildcard"):
        load_roles(path)


def test_unknown_role_raises(tmp_path):
    path = write_roles(tmp_path, ROLES)

    with pytest.raises(PolicyError, match="No role 'coo' defined"):
        build_policy("coo", path)


async def test_dead_rules_are_reported_not_raised(tmp_path, monkeypatch):
    path = write_roles(tmp_path, """
version: 1
roles:
  ceo:
    allow: ["analytics.get_overview", "ghost.tool"]
    deny: ["analytics.gone"]
""")
    policy = build_policy("ceo", path)
    monkeypatch.setattr("gateway.catalog.TOOL_ACCESS", {"analytics": {"get_overview": "read"}})
    catalog = await build_catalog({"analytics": FakeSession([tool("get_overview")])})

    problems = policy.validate_against_catalog(catalog)

    assert len(problems) == 2
    assert any("ghost.tool" in p for p in problems)
    assert any("analytics.gone" in p for p in problems)
    # Reported, but the policy still works: dead rules cannot open a hole.
    assert policy.is_allowed("analytics.get_overview") is True


# ---------------------------------------------------------------------------
# catalog: the TOOL_ACCESS guard
# ---------------------------------------------------------------------------


async def test_unclassified_tool_fails_the_build(monkeypatch):
    monkeypatch.setattr(
        "gateway.catalog.TOOL_ACCESS",
        {"support": {"get_ticket": "read"}},
    )
    sessions = {"support": FakeSession([tool("get_ticket"), tool("shiny_new_tool")])}

    with pytest.raises(CatalogError) as exc:
        await build_catalog(sessions)

    message = str(exc.value)
    assert "shiny_new_tool" in message
    # The message has to be actionable: it names the file and offers the line.
    assert "gateway/catalog.py" in message
    assert "read | write | public_write" in message


async def test_unknown_server_fails_the_build(monkeypatch):
    monkeypatch.setattr("gateway.catalog.TOOL_ACCESS", {"support": {"get_ticket": "read"}})
    sessions = {"email": FakeSession([tool("send_email")])}

    with pytest.raises(CatalogError, match="has no entry in TOOL_ACCESS"):
        await build_catalog(sessions)


async def test_stale_classification_warns_but_builds(monkeypatch, caplog):
    monkeypatch.setattr(
        "gateway.catalog.TOOL_ACCESS",
        {"support": {"get_ticket": "read", "renamed_away": "write"}},
    )
    sessions = {"support": FakeSession([tool("get_ticket")])}

    with caplog.at_level(logging.WARNING):
        catalog = await build_catalog(sessions)

    assert len(catalog) == 1
    assert "renamed_away" in caplog.text


async def test_access_levels_come_from_the_table(monkeypatch):
    monkeypatch.setattr(
        "gateway.catalog.TOOL_ACCESS",
        {"social": {"get_post": "read", "login": "write", "create_post": "public_write"}},
    )
    sessions = {"social": FakeSession([tool("get_post"), tool("login"), tool("create_post")])}

    catalog = await build_catalog(sessions)

    assert catalog.get("social.login").access == "write"
    assert catalog.get("social.create_post").access == "public_write"
    assert catalog.access_counts() == {"read": 1, "write": 1, "public_write": 1}


async def test_colliding_names_stay_distinct(monkeypatch):
    """The reason namespacing is mandatory: same name, two servers, two schemas."""
    monkeypatch.setattr(
        "gateway.catalog.TOOL_ACCESS",
        {"social": {"get_post": "read"}, "analytics": {"get_post": "read"}},
    )
    sessions = {
        "social": FakeSession([tool("get_post", {"type": "object",
                                                 "properties": {"post_id": {"type": "string"}}})]),
        "analytics": FakeSession([tool("get_post", {"type": "object",
                                                    "properties": {"id": {"type": "string"}}})]),
    }

    catalog = await build_catalog(sessions)

    assert len(catalog) == 2
    assert "post_id" in catalog.get("social.get_post").input_schema["properties"]
    assert "id" in catalog.get("analytics.get_post").input_schema["properties"]


# ---------------------------------------------------------------------------
# Adding a server takes three edits and no code change
# ---------------------------------------------------------------------------


async def test_fourth_server_needs_no_code_change(tmp_path, monkeypatch):
    """A new MCP server is three edits: registry YAML, TOOL_ACCESS, roles.yaml.

    This test performs exactly those three and asserts the server flows through
    registry -> catalog -> policy with nothing in gateway/ modified. If this test
    ever needs a fourth edit inside gateway/, that is a design regression.
    """
    # EDIT 1: a block in mcp_servers.yaml.
    registry_path = write_registry(tmp_path, TWO_SERVER_REGISTRY + """
  - id: email
    timeout_seconds: 20.0
    urls:
      docker: http://email-service:8020/mcp
      local: http://localhost:8020/mcp
""")

    configs = load_registry(registry_path, profile="local")
    assert [c.id for c in configs] == ["support", "social", "email"]
    email_config = configs[-1]
    assert email_config.url == "http://localhost:8020/mcp"
    assert email_config.timeout_seconds == 20.0

    # EDIT 2: its tools classified in TOOL_ACCESS.
    monkeypatch.setattr("gateway.catalog.TOOL_ACCESS", {
        **TOOL_ACCESS,
        "email": {"send_email": "public_write", "list_inbox": "read", "get_message": "read"},
    })
    sessions = {"email": FakeSession(
        [tool("send_email"), tool("list_inbox"), tool("get_message")]
    )}

    catalog = await build_catalog(sessions)
    assert len(catalog) == 3
    assert catalog.get("email.send_email").access == "public_write"
    assert qualify("email", "list_inbox") == "email.list_inbox"

    # EDIT 3: a grant in roles.yaml.
    roles_path = write_roles(tmp_path, """
version: 1
roles:
  ceo:
    allow:
      - "email.list_inbox"
      - "email.get_message"
""")
    policy = build_policy("ceo", roles_path)

    visible = {e.qualified_name for e in policy.visible_tools(catalog)}
    assert visible == {"email.list_inbox", "email.get_message"}
    # Not granted, so hidden -- the fail-safe direction.
    assert policy.is_allowed("email.send_email") is False
    assert policy.validate_against_catalog(catalog) == []


# ---------------------------------------------------------------------------
# router: LangChain name mapping
# ---------------------------------------------------------------------------


def test_to_langchain_name_removes_dots():
    assert to_langchain_name("support.patch_ticket") == "support__patch_ticket"
    assert "." not in to_langchain_name("analytics.get_hashtag_posts")


async def test_langchain_name_round_trip(tmp_path, monkeypatch):
    """Every catalog name survives the trip out to LangChain and back."""
    monkeypatch.setattr("gateway.catalog.TOOL_ACCESS", {
        "social": {"get_post": "read", "create_post": "public_write"},
        "analytics": {"get_post": "read"},
    })
    sessions = {
        "social": FakeSession([tool("get_post"), tool("create_post")]),
        "analytics": FakeSession([tool("get_post")]),
    }
    catalog = await build_catalog(sessions)
    router = _router(catalog, tmp_path)

    for entry in catalog:
        mangled = to_langchain_name(entry.qualified_name)
        assert "." not in mangled
        # Both spellings resolve to the qualified name.
        assert router._resolve_name(mangled) == entry.qualified_name
        assert router._resolve_name(entry.qualified_name) == entry.qualified_name

    # The collision survives mangling: two distinct tools, two distinct names.
    assert to_langchain_name("social.get_post") != to_langchain_name("analytics.get_post")


def _router(catalog, tmp_path, **kwargs) -> Router:
    """A Router with a stub connection layer and a temp audit path.

    The audit path matters: the default would create ceo_agent/logs/ as a side
    effect of running the unit tests.
    """
    roles_path = write_roles(tmp_path, """
version: 1
roles:
  ceo:
    allow: ["support.*", "social.*", "analytics.*"]
""")
    import gateway.router as router_module

    original = router_module.build_policy
    router_module.build_policy = lambda role: original(role, roles_path)
    try:
        return Router(object(), catalog, role="ceo",
                      audit_path=tmp_path / "audit.jsonl", **kwargs)
    finally:
        router_module.build_policy = original


# ---------------------------------------------------------------------------
# router: schema preparation
# ---------------------------------------------------------------------------

# Shaped like the real thing: FastMCP renders Optional[str] as an anyOf with a
# null branch and a null default.
PATCH_TICKET_SCHEMA = {
    "type": "object",
    "title": "patch_ticketArguments",
    "properties": {
        "ticket_id": {"type": "string", "title": "Ticket Id"},
        "status": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "title": "Status",
        },
        "priority": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "title": "Priority",
        },
        "reply_message": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
        },
        "actor": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "title": "Actor",
        },
    },
    "required": ["ticket_id", "actor"],
}


def patch_ticket_entry() -> ToolEntry:
    return ToolEntry(
        qualified_name="support.patch_ticket",
        server_id="support",
        tool_name="patch_ticket",
        access="write",
        description="Update a ticket.",
        input_schema=copy.deepcopy(PATCH_TICKET_SCHEMA),
    )


def test_actor_is_stripped_from_properties_and_required():
    schema = prepare_schema(patch_ticket_entry())

    assert "actor" not in schema["properties"]
    assert "actor" not in schema["required"]
    # Everything else survives untouched.
    assert schema["required"] == ["ticket_id"]
    assert "ticket_id" in schema["properties"]
    assert "reply_message" in schema["properties"]


def test_enums_are_injected_on_the_string_branch_only():
    schema = prepare_schema(patch_ticket_entry())

    status = schema["properties"]["status"]
    branches = {b.get("type"): b for b in status["anyOf"]}

    assert branches["string"]["enum"] == ["open", "in_progress", "escalated", "resolved", "closed"]
    # The null branch and the null default must stay legal.
    assert "enum" not in branches["null"]
    assert status["default"] is None
    assert "enum" not in status

    priority = {b.get("type"): b for b in schema["properties"]["priority"]["anyOf"]}
    assert priority["string"]["enum"] == ["low", "medium", "high", "critical"]


def test_unconstrained_parameters_are_left_alone():
    schema = prepare_schema(patch_ticket_entry())

    assert "enum" not in schema["properties"]["reply_message"]["anyOf"][0]
    assert schema["properties"]["ticket_id"] == {"type": "string", "title": "Ticket Id"}


def test_enum_injection_handles_a_plain_string_property():
    entry = ToolEntry(
        qualified_name="support.create_ticket",
        server_id="support",
        tool_name="create_ticket",
        access="write",
        input_schema={
            "type": "object",
            "properties": {
                "issue_type": {"type": "string"},
                "priority": {"type": "string"},
            },
        },
    )

    schema = prepare_schema(entry)

    assert schema["properties"]["issue_type"]["enum"] == [
        "quality", "delivery", "billing", "general", "safety_concern",
    ]
    assert schema["properties"]["priority"]["enum"] == ["low", "medium", "high", "critical"]


def test_prepare_schema_does_not_mutate_the_catalog_entry():
    entry = patch_ticket_entry()

    prepare_schema(entry)

    # The catalog keeps what the server actually said, verbatim.
    assert "actor" in entry.input_schema["properties"]
    assert entry.input_schema == PATCH_TICKET_SCHEMA


def test_missing_enum_parameter_warns_instead_of_failing(caplog):
    """If their team drops a parameter, the table lags -- say so, do not crash."""
    entry = patch_ticket_entry()
    del entry.input_schema["properties"]["status"]

    with caplog.at_level(logging.WARNING):
        schema = prepare_schema(entry)

    assert "status" not in schema["properties"]
    assert "out of date" in caplog.text


def test_tools_with_no_injections_pass_through_unchanged():
    entry = ToolEntry(
        qualified_name="analytics.get_overview",
        server_id="analytics",
        tool_name="get_overview",
        access="read",
        input_schema={"type": "object", "properties": {"days": {"type": "integer"}}},
    )

    assert prepare_schema(entry) == entry.input_schema

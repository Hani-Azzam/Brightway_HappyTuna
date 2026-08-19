"""Integration tests. These need the live MCP servers.

    docker compose up -d social-network customer-support-mcp
    pytest ceo_agent/tests/test_integration.py

Skipped cleanly, with instructions, when nothing is reachable -- see the
`gateway` fixture in conftest.py. Partial connectivity is not skipped: a server
that is down when the others are up is a real failure, and
`test_all_servers_connect` is meant to catch it.

Read-only by default: no tickets, no posts, no messages. The write tests are
marked `writes` and deselected by pytest.ini's addopts. To run them:

    pytest ceo_agent/tests/test_integration.py -m writes

They leave rows in the real Customer Support database (a ticket and its patch)
and in the real chat store (a channel and a message). Each proves an identity
guarantee that cannot be proved read-only: that the injected actor reaches the
support activity log, and that the chat session's login binding survives across
calls. The chat rows are the more expensive of the two -- that server has no
delete_channel and no remove_member, so they are permanent.

The `smoke` tests are deselected too, for a different reason -- not danger but
cost. They call every read tool on the CEO's surface, one round trip each:

    pytest ceo_agent/tests/test_integration.py -m smoke -s
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from gateway.connection import call_tool as raw_call
from gateway.router import Router

pytestmark = pytest.mark.integration


# The surface as recorded when this was written. These four numbers are the only
# things here that need updating when a server is added or a team ships a tool --
# see the invariant tests below, which never do. A failure here is either an
# upstream change worth knowing about, or an intended change worth recording.
RECORDED_SERVERS = 4
RECORDED_TOOLS = 48
RECORDED_VISIBLE = 30
RECORDED_HIDDEN = RECORDED_TOOLS - RECORDED_VISIBLE  # 18


@pytest.fixture()
def router(gateway, tmp_path) -> Router:
    """A CEO router writing its audit log somewhere disposable."""
    return Router(gateway.connections, gateway.catalog, role="ceo",
                  audit_path=tmp_path / "audit.jsonl")


@pytest.fixture()
def dry_router(gateway, tmp_path) -> Router:
    return Router(gateway.connections, gateway.catalog, role="ceo",
                  dry_run=True, audit_path=tmp_path / "audit.jsonl")


def audit_records(path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# connection
# ---------------------------------------------------------------------------


def test_all_servers_connect(gateway):
    statuses = gateway.statuses
    down = [s for s in statuses if not s.connected]

    assert not down, "not connected: " + "; ".join(
        f"{s.server_id} ({s.skipped_reason})" for s in down
    )
    assert len(statuses) == RECORDED_SERVERS


def test_social_login_ran_and_bound_an_identity(gateway):
    """Writes 401 until login populates the session's closure state."""
    social = next(s for s in gateway.statuses if s.server_id == "social")

    assert social.login_attempted is True
    assert social.login_ok is True
    assert social.identity, "login returned no token; later writes would be unauthored"


def test_servers_with_no_login_report_not_applicable(gateway):
    analytics = next(s for s in gateway.statuses if s.server_id == "analytics")

    # None means "nothing configured", not "ran and failed".
    assert analytics.login_attempted is False
    assert analytics.login_ok is None


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


def test_catalog_size_matches_the_recorded_surface(gateway):
    assert len(gateway.catalog) == RECORDED_TOOLS
    assert len(gateway.catalog.server_ids) == RECORDED_SERVERS


def test_every_live_tool_is_classified(gateway):
    """Invariant. Needs no update when a server is added -- build_catalog raises."""
    assert all(entry.access in ("read", "write", "public_write") for entry in gateway.catalog)


def test_colliding_names_are_namespaced(gateway):
    """The three names that exist on two servers each, with different schemas."""
    for name in ("search", "get_post", "get_hashtag_posts"):
        social = gateway.catalog.get(f"social.{name}")
        analytics = gateway.catalog.get(f"analytics.{name}")
        assert social is not None, f"social.{name} missing"
        assert analytics is not None, f"analytics.{name} missing"
        assert social.tool_name == analytics.tool_name == name


def test_the_two_irreversible_tools_are_tagged_public_write(gateway):
    public = {e.qualified_name for e in gateway.catalog.by_access("public_write")}

    assert public == {"social.create_post", "social.add_comment"}


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------


def test_ceo_surface_matches_the_recorded_size(router, gateway):
    visible = router.get_tools()

    assert len(visible) == RECORDED_VISIBLE
    assert len(gateway.catalog) - len(visible) == RECORDED_HIDDEN


def test_operator_controls_are_hidden(router):
    visible = {entry.qualified_name for entry in router.get_tools()}

    # Instruments the CEO is scored by, identity rebinding, and ticket fabrication.
    for name in ("analytics.run_analysis", "analytics.set_ai_analysis",
                 "social.login", "social.set_account_type", "support.create_ticket"):
        assert name not in visible, f"{name} is visible to the CEO"


def test_no_dead_rules(router, gateway):
    """Invariant. Fails when a team renames a tool roles.yaml still names."""
    from gateway.policy import build_policy

    problems = build_policy("ceo").validate_against_catalog(gateway.catalog)

    assert problems == [], "; ".join(problems)


def test_langchain_tools_match_the_visible_surface(router):
    tools = router.get_langchain_tools()

    assert len(tools) == len(router.get_tools())
    assert all("." not in t.name for t in tools)
    names = {t.name for t in tools}
    assert "analytics__run_analysis" not in names


# ---------------------------------------------------------------------------
# router: real calls
# ---------------------------------------------------------------------------


def _first_argless_read(router) -> str:
    """A visible read tool that needs no arguments, preferring the cheap ones."""
    specs = {s["name"]: s for s in router.get_tools_for_llm()}
    preferred = ["analytics.get_analysis_status", "analytics.get_overview",
                 "social.get_global_feed", "social.get_trending_hashtags"]
    candidates = preferred + sorted(specs)

    for name in candidates:
        spec = specs.get(name)
        if spec and not spec["input_schema"].get("required"):
            entry = next(e for e in router.get_tools() if e.qualified_name == name)
            if entry.access == "read":
                return name
    pytest.skip("no argument-free read tool in the visible surface")


async def test_a_real_read_succeeds(router):
    name = _first_argless_read(router)

    result = await router.call_tool(name, {})

    assert result.ok is True, f"{name} failed: {result.error}"
    assert result.is_error is False
    assert result.text is not None or result.data is not None
    assert result.elapsed_ms > 0


async def test_denied_call_returns_failure_and_never_dispatches(router, tmp_path):
    result = await router.call_tool("analytics.run_analysis", {})

    assert result.ok is False
    assert "not available to role 'ceo'" in result.error
    assert result.qualified_name == "analytics.run_analysis"

    end = [r for r in audit_records(tmp_path / "audit.jsonl") if r["event"] == "call_end"]
    assert end[-1]["outcome"] == "denied"


async def test_denied_call_is_blocked_under_either_spelling(router):
    """The LangChain spelling resolves to the same name, so it is denied too."""
    result = await router.call_tool("analytics__run_analysis", {})

    assert result.ok is False


async def test_unknown_name_returns_failure(router, tmp_path):
    """Note the server: roles.yaml grants "support.*", so this name satisfies the
    policy and is stopped by the catalog check instead. The error must say so
    rather than blaming the connection."""
    result = await router.call_tool("support.delete_everything", {})

    assert result.ok is False
    assert "No such tool" in result.error
    assert "not connected" not in result.error

    end = [r for r in audit_records(tmp_path / "audit.jsonl") if r["event"] == "call_end"]
    assert end[-1]["outcome"] == "unknown_tool"


async def test_dry_run_does_not_reach_the_server(dry_router, tmp_path):
    args = {"content": "pytest dry run -- this must never be published"}

    result = await dry_router.call_tool("social.create_post", args)

    assert result.ok is True
    assert result.data == {"dry_run": True, "would_send": args}
    # Nothing came back from a server, because nothing was sent.
    assert result.text is None
    assert result.is_error is False

    end = [r for r in audit_records(tmp_path / "audit.jsonl") if r["event"] == "call_end"]
    assert end[-1]["outcome"] == "dry_run"


async def test_dry_run_holds_back_plain_writes_too(dry_router, tmp_path):
    """The regression guard for a gap that shipped once already.

    The gate used to test `access == "public_write"`, so a dry run published
    nothing but still patched real tickets and, once chat arrived, could open a
    channel on a server with no delete_channel. The test above did not catch it
    because it only ever exercised a public_write, which is precisely how the gap
    survived. This one asserts the other level.

    chat.create_channel is the case that matters: its arguments here are valid, so
    if the gate narrows again this test does not merely fail -- it creates a
    channel that cannot be removed. That is the cost of proving it, and the reason
    the assertion is worth having rather than trusting the constructor's warning.
    """
    args = {"type": "incident", "members": ["COO-1"],
            "name": "pytest -- must never be created"}

    result = await dry_router.call_tool("chat.create_channel", args)

    assert result.ok is True, result.error
    assert result.data == {"dry_run": True, "would_send": args}
    assert result.text is None, f"chat.create_channel reached the server: {result.text!r}"

    end = [r for r in audit_records(tmp_path / "audit.jsonl") if r["event"] == "call_end"][-1]
    assert end["outcome"] == "dry_run"
    assert end["access"] == "write", "the point of this test is the non-public level"


async def test_dry_run_still_lets_reads_through(dry_router):
    name = _first_argless_read(dry_router)

    result = await dry_router.call_tool(name, {})

    assert result.ok is True
    assert result.data != {"dry_run": True}


def test_get_status_reports_every_configured_server(router):
    statuses = router.get_status()

    assert len(statuses) == RECORDED_SERVERS
    assert {s.server_id for s in statuses} == {"support", "analytics", "social", "chat"}


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


async def test_every_call_writes_a_start_and_an_end(router, tmp_path):
    path = tmp_path / "audit.jsonl"
    name = _first_argless_read(router)

    await router.call_tool(name, {})
    await router.call_tool("analytics.run_analysis", {})       # denied
    await router.call_tool("support.delete_everything", {})    # unknown

    records = audit_records(path)
    starts = [r for r in records if r["event"] == "call_start"]
    ends = [r for r in records if r["event"] == "call_end"]

    assert len(starts) == len(ends) == 3
    # Paired by call_id, one start per end.
    assert {r["call_id"] for r in starts} == {r["call_id"] for r in ends}
    assert all(r["role"] == "ceo" for r in records)
    # The two calls that never dispatched are recorded just like the one that did.
    assert {r["outcome"] for r in ends} == {"ok", "denied", "unknown_tool"}


async def test_audit_records_the_access_level_and_timing(router, tmp_path):
    name = _first_argless_read(router)

    await router.call_tool(name, {})

    end = [r for r in audit_records(tmp_path / "audit.jsonl") if r["event"] == "call_end"][-1]
    assert end["access"] == "read"
    assert end["ok"] is True
    assert end["elapsed_ms"] > 0
    assert "timestamp" in end


# ---------------------------------------------------------------------------
# smoke -- off by default: `pytest ceo_agent/tests/test_integration.py -m smoke`
# ---------------------------------------------------------------------------
#
# Everything above proves the gateway is correct: the catalog is complete, the
# policy holds, a call is routed and audited. None of it proves the servers on
# the other end answer. A tool can be catalogued, permitted, and schema-correct
# and still 500 on every call -- the CEO would face a surface that looks whole
# and is hollow, and nothing here would notice, because the one real read above
# deliberately picks the cheapest argument-free tool it can find.
#
# So: call every read tool once, report what came back. One round trip per tool
# and a dependence on seeded data, which is why it is behind a marker rather
# than in the default run.


#: Read tools that need an argument no schema can supply, where any value will
#: do: these query, and a query matching nothing still comes back 200 from a
#: live server. Ids are the opposite -- a made-up one 404s and proves nothing --
#: so those are resolved from live data in `_resolve_smoke_args` instead.
#:
#: get_hashtag_posts belongs here rather than there: an unknown tag returns an
#: empty list, not an error (`hashtagService.ts:15`). The resolver still prefers
#: a real trending tag when the platform has one.
#: Parameters the router injects, which therefore appear in a dry run's
#: `would_send` without the caller having passed them. Mirrors INJECTED_PARAMS in
#: router.py; kept here as a literal so the test states the expected value rather
#: than importing the thing it is checking.
INJECTED_ON_DRY_RUN: dict[str, dict[str, Any]] = {
    "support.patch_ticket": {"actor": "ceo"},
}

SMOKE_LITERAL_ARGS: dict[str, dict[str, Any]] = {
    "analytics.search": {"q": "tuna"},
    "social.search": {"q": "tuna"},
    "analytics.get_hashtag_posts": {"tag": "tuna"},
}


def _first_value(payload: Any, key: str) -> str | None:
    """The first non-empty string under `key`, depth-first.

    Walks the payload rather than assuming its shape: social returns a bare
    array, support returns `{"count", "tickets"}`, and hard-coding either would
    make this fail for a reason that has nothing to do with the servers.

    Depth-first order is load-bearing. A post carries its author inline, and a
    dict is checked for `key` before its children are, so a post's own "id" is
    always reached before the author's -- the ids never cross.
    """
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        for nested in payload.values():
            found = _first_value(nested, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _first_value(item, key)
            if found is not None:
                return found
    return None


async def _resolve_smoke_args(router) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Live arguments for the read tools that need one, and why any were skipped.

    Returns `(args by qualified name, skip reason by qualified name)`. An empty
    database is a skip, not a failure: `get_ticket` cannot be blamed for there
    being no tickets, and a smoke run against a fresh database should still
    report on the other twenty tools.
    """
    args: dict[str, dict[str, Any]] = {n: dict(a) for n, a in SMOKE_LITERAL_ARGS.items()}
    skips: dict[str, str] = {}

    async def resolve(source: str, key: str, targets: dict[str, str], what: str) -> None:
        """Reads one listing tool and fans its first id out to the tools needing it.

        Tools already carrying a literal keep it if nothing can be resolved --
        only the ones with no usable argument at all are skipped.
        """
        result = await router.call_tool(source, {})
        if not result.ok:
            reason = f"could not resolve a {what}: {source} failed ({result.error})"
        else:
            value = _first_value(result.data, key)
            if value is not None:
                for target, param in targets.items():
                    args[target] = {param: value}
                return
            reason = f"no {what} in the live data: {source} returned none"
        for target in targets:
            if target not in args:
                skips[target] = reason

    await resolve("support.list_tickets", "ticket_id", {
        "support.get_ticket": "ticket_id",
        "support.get_activity_log": "ticket_id",
    }, "ticket id")
    await resolve("social.get_global_feed", "id", {
        "social.get_post": "id",
        "analytics.get_post": "id",
        "social.get_comments": "postId",
    }, "post id")
    await resolve("analytics.get_top_influencers", "id", {
        "social.get_user": "id",
    }, "user id")
    await resolve("social.get_trending_hashtags", "tag", {
        "analytics.get_hashtag_posts": "tag",
    }, "hashtag")
    # Chat ids are resolved, never literal: the server answers a channel the CEO
    # is not a member of exactly as it answers one that does not exist
    # (service.py:79-81), so a made-up id would look like a clean failure and
    # prove nothing. CEO-1 is seeded into at least one channel by the chat stack,
    # so on a seeded database this resolves; on an empty one it skips rather than
    # failing, like every other resolver here.
    await resolve("chat.list_channels", "channel", {
        "chat.read_channel": "channel",
    }, "chat channel id")

    return args, skips


@pytest.mark.smoke
async def test_every_read_tool_responds(router):
    """Calls all 24 read tools on the CEO's surface and reports which answered."""
    reads = sorted((e for e in router.get_tools() if e.access == "read"),
                   key=lambda e: e.qualified_name)
    assert reads, "no read tools are visible to the CEO"

    args_by_tool, skips = await _resolve_smoke_args(router)

    lines: list[str] = []
    failures: list[str] = []
    uncallable: list[str] = []
    responded = 0

    for entry in reads:
        name = entry.qualified_name

        if name in skips:
            lines.append(f"  skip            {name} -- {skips[name]}")
            continue

        args = args_by_tool.get(name, {})
        shown = json.dumps(args, sort_keys=True)
        missing = [p for p in entry.input_schema.get("required", []) if p not in args]
        if missing:
            lines.append(f"  ????            {name} -- no value for {', '.join(missing)}")
            uncallable.append(f"{name} requires {missing}, which nothing supplies")
            continue

        result = await router.call_tool(name, args)

        if result.ok:
            responded += 1
            lines.append(f"  ok     {result.elapsed_ms:7.1f}ms  {name} {shown}")
        else:
            lines.append(f"  FAIL   {result.elapsed_ms:7.1f}ms  {name} {shown} -- {result.error}")
            # Named with the args, so a broken upstream tool is distinguishable
            # from a wrong argument on our side without a second run.
            failures.append(f"{name} called with {shown} -- {result.error}")

    skipped = sum(1 for e in reads if e.qualified_name in skips)
    report = "\n".join([
        f"{responded} of {len(reads)} read tools responded "
        f"({len(failures)} failed, {skipped} skipped, {len(uncallable)} uncallable)",
        *lines,
    ])
    print("\n" + report)

    assert not uncallable, (
        "the smoke test cannot call every read tool the CEO can see, so it is no "
        "longer proof of the whole surface. Add a literal to SMOKE_LITERAL_ARGS, "
        "or resolve one from live data in _resolve_smoke_args:\n  "
        + "\n  ".join(uncallable) + "\n\n" + report
    )
    assert not failures, (
        "read tools that did not respond:\n  " + "\n  ".join(failures) + "\n\n" + report
    )


@pytest.mark.smoke
async def test_the_write_tools_are_present_and_tagged_without_being_called(dry_router):
    """The rest of the surface, asserted without writing anything.

    Six writes, and this test calls none of them for real: the dry-run gate
    covers every one, which is itself the assertion. The arguments below are
    fabricated, so a regression that let them through would fail on a 404 rather
    than put words in the CEO's mouth -- except chat.create_channel, whose
    arguments are perfectly valid and which would succeed.

    So the order below is load-bearing, not alphabetical. Every call before
    chat.create_channel names something that does not exist, and each is asserted
    before the next runs. If the gate ever narrows back to public_write, one of
    those fails first and aborts the loop, so the one call that would leave a
    permanent channel on a server with no delete_channel is never reached. Keep
    chat.create_channel last.
    """
    access_by_name = {e.qualified_name: e.access for e in dry_router.get_tools()}
    writes = {n: a for n, a in access_by_name.items() if a != "read"}

    assert writes == {
        "social.create_post": "public_write",
        "social.add_comment": "public_write",
        "support.patch_ticket": "write",
        "chat.send_message": "write",
        "chat.create_channel": "write",
        "chat.add_member": "write",
    }

    for name, args in (
        ("social.create_post", {"content": "pytest smoke -- must never be published"}),
        ("social.add_comment", {"postId": "smoke-no-such-post",
                                "content": "pytest smoke -- must never be published"}),
        ("support.patch_ticket", {"ticket_id": "SMOKE-NO-SUCH-TICKET",
                                  "status": "in_progress"}),
        ("chat.send_message", {"channel": "smoke-no-such-channel",
                               "body": "pytest smoke -- must never be sent"}),
        ("chat.add_member", {"channel": "smoke-no-such-channel", "agent_id": "COO-1"}),
        # Last, and valid: see the docstring. Everything above is a canary for it.
        ("chat.create_channel", {"type": "incident", "members": ["COO-1"],
                                 "name": "pytest smoke -- must never be created"}),
    ):
        result = await dry_router.call_tool(name, args)

        # `would_send` is what the server would have received, which is not always
        # what the caller passed: identity injection has already run by this point,
        # so support.patch_ticket carries the actor the CEO cannot set itself. That
        # is the useful thing about the payload -- a dry run shows the injected
        # value, so the guarantee can be inspected without writing a ticket.
        expected = dict(args) | INJECTED_ON_DRY_RUN.get(name, {})

        assert result.ok is True, f"{name} -- {result.error}"
        assert result.data == {"dry_run": True, "would_send": expected}
        # Nothing came back because nothing was sent.
        assert result.text is None, f"{name} reached the server: {result.text!r}"


# ---------------------------------------------------------------------------
# writes -- off by default: `pytest ceo_agent/tests/test_integration.py -m writes`
# ---------------------------------------------------------------------------


@pytest.mark.writes
async def test_actor_is_injected_as_ceo_on_a_real_ticket(gateway, router, tmp_path):
    """Proves identity injection reaches the Customer Support activity log.

    Leaves a ticket and its log entries in the real database. The ticket is
    created through the raw connection layer, not the router, because
    support.create_ticket is denied to the CEO -- fabricating a complaint is
    exactly what the policy forbids. That makes this a test harness acting as the
    environment, not the agent doing something it is not allowed to do.
    """
    session = gateway.connections.session_for("support")
    config = gateway.connections.config_for("support")
    assert session is not None, "support server not connected"

    created = await raw_call(session, config, "create_ticket", {
        "customer_id": "PYTEST-HARNESS",
        "issue_type": "quality",
        "subject": "pytest fixture ticket -- safe to delete",
        "description": "pytest: verifying gateway actor injection. Safe to delete.",
    })
    assert created.ok, f"harness could not create a ticket: {created.error}"
    ticket_id = (created.data or {}).get("ticket_id")
    assert ticket_id, f"no ticket_id in {created.data!r}"

    async def entries() -> list[dict]:
        log = await router.call_tool("support.get_activity_log", {"ticket_id": ticket_id})
        assert log.ok is True, log.error
        return (log.data or {}).get("entries", [])

    # The rows the harness itself produced. Creation is filed under "system"
    # because the harness passes no actor -- that is the upstream default this
    # guarantee exists to override, and it is not what is under test here.
    before = await entries()

    # The agent path: note that `actor` is not passed, and cannot be.
    patched = await router.call_tool("support.patch_ticket", {
        "ticket_id": ticket_id,
        "status": "in_progress",
        "reply_message": "pytest: gateway integration test",
    })
    assert patched.ok is True, patched.error

    after = await entries()
    new_rows = after[len(before):]

    assert new_rows, "the patch produced no activity log entries"
    actors = {row.get("actor") for row in new_rows}
    assert actors == {"ceo"}, (
        f"every row the patch produced should be filed under 'ceo', got {actors}. "
        f"'system' here means identity injection did not apply."
    )

    # And the audit log recorded the injected value, not what the caller sent.
    end = [r for r in audit_records(tmp_path / "audit.jsonl")
           if r["event"] == "call_end" and r["qualified_name"] == "support.patch_ticket"][-1]
    assert end["args"]["actor"] == "ceo"


def _chat_payload(result) -> dict:
    """The chat server's own result envelope, unwrapped and checked.

    Two `ok` flags stack on every chat call and only one of them is the gateway's.
    The outer `ToolResult.ok` says the call reached the server and came back
    without a transport error; the chat server then reports its own
    `{ok, tool, value, error}` envelope in the body (mcp_server.py returns the raw
    envelope deliberately). A permission or membership rejection comes back as a
    *successful* call carrying `ok: false`, so asserting the outer flag alone
    would pass on a 403 and read as proof of something it never tested.
    """
    assert result.ok is True, f"{result.qualified_name}: {result.error}"
    payload = result.data
    assert isinstance(payload, dict), (
        f"{result.qualified_name} returned no JSON envelope: {result.text!r}"
    )
    assert payload.get("ok") is True, (
        f"{result.qualified_name} was rejected by the chat server: {payload.get('error')!r}"
    )
    value = payload.get("value")
    assert isinstance(value, dict), f"{result.qualified_name} envelope has no value: {payload!r}"
    return value


@pytest.mark.writes
async def test_chat_identity_binding_holds_across_calls(router):
    """Proves the CEO's chat identity survives from one call to the next.

    The chat counterpart of the actor-injection test above, and a different
    mechanism with the same failure mode. Support identity is injected into the
    arguments of every call, so each call carries its own proof. Chat identity is
    bound once, to the MCP *session*, by the login connection.py runs at startup
    (`mcp_server.py` keys it on the `ServerSession` in a `WeakKeyDictionary`), and
    every later call on that session inherits it. Nothing else in this file
    exercises that: a binding that silently dropped would surface as messages
    authored by the wrong agent, or as a 401 mid-crisis, and the read-only tests
    would all still pass.

    So: open a channel, post to it, read it back, and check the server agrees the
    author was CEO-1 -- three separate calls, none of which passes an identity.

    Leaves a channel and a message in the real chat store, and neither can be
    removed: that server has no delete_channel and no remove_member. This is why
    the test is behind the `writes` marker, and why the chat stack needs resetting
    between trials. See README gotchas.
    """
    marker = f"pytest gateway integration -- safe to ignore [{uuid4().hex[:12]}]"

    created = await router.call_tool("chat.create_channel", {
        "type": "incident",
        "members": ["COO-1"],
        "name": "pytest fixture channel -- safe to ignore",
    })
    channel = _chat_payload(created).get("channel")
    assert channel, f"no channel id in {created.data!r}"

    # Note what is absent from both calls: any sender, author, or agent_id. The
    # only place CEO-1 appears in this whole exchange is mcp_servers.yaml.
    sent = await router.call_tool("chat.send_message", {"channel": channel, "body": marker})
    _chat_payload(sent)

    history = await router.call_tool("chat.read_channel", {"channel": channel})
    messages = _chat_payload(history).get("messages")
    assert isinstance(messages, list), f"no messages list in {history.data!r}"

    # Matched on the marker rather than taking messages[-1]: the channel is fresh,
    # but a seeded or concurrently-written one would make position meaningless.
    mine = [m for m in messages if m.get("body") == marker]
    assert mine, (
        f"the message did not come back from the channel it was posted to. "
        f"Sent {marker!r}, read back {[m.get('body') for m in messages]!r}"
    )
    assert len(mine) == 1, f"the marker came back {len(mine)} times: {mine!r}"

    assert mine[0].get("sender") == "CEO-1", (
        f"the message came back authored by {mine[0].get('sender')!r}, not 'CEO-1'. "
        f"The session's login binding did not survive from create_channel to "
        f"send_message -- every write the CEO makes in chat is misattributed."
    )


def test_advertised_schema_hides_actor(router):
    """The other half of the guarantee: the model is never shown the parameter.

    Read-only, so this one runs by default -- only the ticket-writing half above
    is behind the marker.
    """
    spec = next(s for s in router.get_tools_for_llm() if s["name"] == "support.patch_ticket")

    assert "actor" not in spec["input_schema"]["properties"]
    assert "actor" not in spec["input_schema"].get("required", [])
    status = spec["input_schema"]["properties"]["status"]
    branches = [b for b in status.get("anyOf", [status]) if b.get("type") == "string"]
    assert branches and "escalated" in branches[0]["enum"]

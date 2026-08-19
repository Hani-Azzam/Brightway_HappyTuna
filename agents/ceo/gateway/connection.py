""" 

Every session is entered into a single `AsyncExitStack`, so the whole set is torn
down together and in reverse order when the gateway exits.

The contract this layer exists to guarantee: **one broken server never takes down
the gateway.** A server that is disabled, unreachable, or that fails its login is
skipped with a WARNING naming the server and the reason, and the remaining
servers still come up. Nothing here is ever silent -- a silently missing server
would make "the CEO chose not to act" indistinguishable from "the CEO could not
reach the system", which would quietly corrupt the study's data.

Session mechanics are handled by the MCP SDK: `streamablehttp_client` captures
the `mcp-session-id` the server mints on `initialize` and replays it on every
later request. No header code belongs here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack, contextmanager
from datetime import timedelta
from types import TracebackType
from typing import Any, Iterator, Sequence

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, Implementation

from .models import ServerConfig, ServerStatus, ToolResult

logger = logging.getLogger(__name__)

CLIENT_NAME = "happytuna-ceo-gateway"
CLIENT_VERSION = "0.1.0"


# These servers belong to other teams and cannot be modified, so a connection
# failure has to be actionable from the WARNING alone, without a debugger.


def describe_exception(exc: BaseException) -> str:
    """Renders an exception as one actionable line.

    Flattens `ExceptionGroup`s (anyio task groups inside the transport raise
    them, and their default repr buries the real cause) and follows `__cause__`
    chains, de-duplicating repeated messages.
    """
    parts: list[str] = []
    seen: set[str] = set()

    def walk(err: BaseException, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(err, BaseExceptionGroup):
            for sub in err.exceptions:
                walk(sub, depth + 1)
            return
        rendered = f"{type(err).__name__}: {err}".strip().rstrip(":")
        if rendered not in seen:
            seen.add(rendered)
            parts.append(rendered)
        if err.__cause__ is not None:
            walk(err.__cause__, depth + 1)

    walk(exc)
    return " <- ".join(parts) if parts else repr(exc)


#: The SDK logger that narrates the server-to-client SSE stream.
_TRANSPORT_LOGGER = "mcp.client.streamable_http"


@contextmanager
def _quiet_transport_teardown() -> Iterator[None]:
    """Suppresses the transport's misleading reconnect chatter while shutting down.

    Closing a session logs "GET stream disconnected, reconnecting in 1000ms..." at
    INFO, but nothing reconnects: the SDK awaits its DELETE before cancelling the
    task group, so the GET stream sees the session end, logs its intent to retry,
    and is cancelled mid-sleep. That loop runs in a task the SDK spawns internally
    and never hands us, and there is no public hook to close the SSE read stream
    early. `terminate_on_close=False` would dodge the message only by skipping the
    DELETE, leaving sessions dangling server-side -- strictly worse.

    So it is suppressed, not prevented: INFO and below, only during teardown. A
    genuine WARNING or ERROR from the transport still comes through.
    """
    logger_obj = logging.getLogger(_TRANSPORT_LOGGER)
    previous_level = logger_obj.level
    logger_obj.setLevel(max(previous_level, logging.WARNING))
    try:
        yield
    finally:
        logger_obj.setLevel(previous_level)


def _is_cancellation(exc: BaseException) -> bool:
    """True when `exc` is a cancellation, or a group containing only cancellations."""
    if isinstance(exc, BaseExceptionGroup):
        return bool(exc.exceptions) and all(_is_cancellation(sub) for sub in exc.exceptions)
    return isinstance(exc, asyncio.CancelledError)


async def _close_quietly(stack: AsyncExitStack) -> BaseException | None:
    """Unwinds a stack, returning whatever it raised instead of propagating it.

    This is where a failed connection's real cause shows up. The Streamable HTTP
    transport runs its HTTP work in an anyio task group, so a refused connection
    cancels the waiting caller -- the body of the `try` sees only a bare
    `CancelledError`, and the underlying `ConnectError` is raised later, while
    the task group unwinds.
    """
    try:
        await stack.aclose()
    except BaseException as exc:  # noqa: BLE001 -- reported, never propagated
        return exc
    return None


def failure_hint(exc: BaseException, cfg: ServerConfig) -> str | None:
    """Maps a connection failure to a concrete next step, when one is obvious."""

    def find(*types: type[BaseException]) -> BaseException | None:
        stack: list[BaseException] = [exc]
        while stack:
            err = stack.pop()
            if isinstance(err, types):
                return err
            if isinstance(err, BaseExceptionGroup):
                stack.extend(err.exceptions)
            if err.__cause__ is not None:
                stack.append(err.__cause__)
        return None

    status_error = find(httpx.HTTPStatusError)
    if isinstance(status_error, httpx.HTTPStatusError):
        code = status_error.response.status_code
        if code == 404:
            return (
                f"the server answered but has no MCP endpoint at this path -- check the "
                f"path portion of {cfg.url}"
            )
        if code in (400, 406):
            return (
                f"the server rejected the initialize request (HTTP {code}); it may not be "
                f"speaking Streamable HTTP at this path"
            )
        return f"the server returned HTTP {code}"

    if find(httpx.ConnectError) is not None:
        # Only suggest switching profile when the URL is clearly the other one,
        # so the hint never tells you to set the profile you are already using.
        is_local_url = "localhost" in cfg.url or "127.0.0.1" in cfg.url
        switch = (
            "if you are running the gateway outside compose, set GATEWAY_URL_PROFILE=local"
            if not is_local_url
            else "if you are running the gateway inside compose, unset GATEWAY_URL_PROFILE"
        )
        return f"nothing is listening on {cfg.url} -- is the service up (docker compose ps)? {switch}"

    if find(httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout, TimeoutError) is not None:
        return (
            f"timed out after {cfg.timeout_seconds}s -- raise timeout_seconds for "
            f"{cfg.id!r} in mcp_servers.yaml if the service is merely slow to start"
        )

    if find(McpError) is not None:
        # A wrong path shows up here rather than as an HTTPStatusError: the SDK
        # turns the 404 into "Session terminated" without surfacing the status.
        return (
            f"the server answered but did not complete the MCP handshake -- most often a wrong "
            f"path (check the path portion of {cfg.url}) or an endpoint that does not speak "
            f"Streamable HTTP"
        )

    return None


def _text_of(raw: CallToolResult) -> str | None:
    """Joins the text content blocks of a tool result."""
    chunks = [block.text for block in raw.content if getattr(block, "type", None) == "text"]
    return "\n".join(chunks) if chunks else None


async def call_tool(
    session: ClientSession,
    cfg: ServerConfig,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> ToolResult:
    """Calls one tool and normalizes the outcome into a `ToolResult`.

    Never raises for a tool-level failure, and never raises for a transport
    failure either -- both come back as `ok=False`. `router.py` will reuse this
    once it exists, so the normalization lives in exactly one place.
    """
    qualified_name = f"{cfg.id}.{tool_name}"
    started = time.perf_counter()

    try:
        raw = await session.call_tool(tool_name, args or {})
    except Exception as exc:  # noqa: BLE001 -- deliberately total; see docstring
        return ToolResult(
            qualified_name=qualified_name,
            server_id=cfg.id,
            tool_name=tool_name,
            ok=False,
            error=describe_exception(exc),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    text = _text_of(raw)
    data: Any | None = None
    if text is not None:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            data = None  # Not every tool returns JSON; the raw text is still in `text`.

    return ToolResult(
        qualified_name=qualified_name,
        server_id=cfg.id,
        tool_name=tool_name,
        ok=not raw.isError,
        is_error=bool(raw.isError),
        text=text,
        data=data,
        # Social and analytics surface service errors as an isError result whose
        # text is the message ("Error 400: ..."), so `text` is the reason here.
        error=None if not raw.isError else (text or "tool reported an error"),
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )


def _extract_identity(data: Any) -> str | None:
    """Pulls the caller's own id out of a login result, if it looks like one.

    Social's `login` returns `{token, user}` where the token *is* the user id
    (`authService.ts:26`). Treated as best-effort diagnostic metadata: an
    unrecognised shape is not an error, it just leaves `identity` unset.
    """
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if isinstance(token, str) and token:
        return token
    user = data.get("user")
    if isinstance(user, dict):
        user_id = user.get("id")
        if isinstance(user_id, str) and user_id:
            return user_id
    return None


class GatewayConnections:
    """Holds one live `ClientSession` per reachable server.

    Use as an async context manager::

        async with GatewayConnections(load_registry()) as conns:
            statuses = await conns.connect_all()
            session = conns.session_for("social")

    Servers are connected sequentially rather than concurrently. With three
    servers the wall-clock difference is negligible, and sequential connection
    keeps the WARNING output attributable to one server at a time.
    """

    def __init__(
        self,
        configs: Sequence[ServerConfig],
        client_name: str = CLIENT_NAME,
        client_version: str = CLIENT_VERSION,
    ) -> None:
        self._configs = list(configs)
        self._client_info = Implementation(name=client_name, version=client_version)
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._statuses: dict[str, ServerStatus] = {}
        self._entered = False

    async def __aenter__(self) -> "GatewayConnections":
        await self._stack.__aenter__()
        self._entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        self._entered = False
        self._sessions.clear()
        with _quiet_transport_teardown():
            return await self._stack.__aexit__(exc_type, exc, tb)

    async def aclose(self) -> None:
        """Closes every session. Equivalent to leaving the context manager."""
        await self.__aexit__(None, None, None)

    @property
    def sessions(self) -> dict[str, ClientSession]:
        """Live sessions, keyed by server id. Only successfully connected servers."""
        return dict(self._sessions)

    @property
    def statuses(self) -> list[ServerStatus]:
        """One status per configured server, in registry order."""
        return [self._statuses[cfg.id] for cfg in self._configs if cfg.id in self._statuses]

    @property
    def connected_count(self) -> int:
        return sum(1 for status in self._statuses.values() if status.connected)

    @property
    def total_count(self) -> int:
        return len(self._configs)

    def session_for(self, server_id: str) -> ClientSession | None:
        """The live session for a server, or None if it never connected."""
        return self._sessions.get(server_id)

    def config_for(self, server_id: str) -> ServerConfig | None:
        """The config for a server, or None if no such server is configured.

        `call_tool` needs the config alongside the session (for the id and the
        timeout), so callers holding only a server id can look both up.
        """
        for cfg in self._configs:
            if cfg.id == server_id:
                return cfg
        return None

    def status_for(self, server_id: str) -> ServerStatus | None:
        return self._statuses.get(server_id)

    async def connect_all(self) -> list[ServerStatus]:
        """Connects every enabled server, skipping any that fails.

        Returns one `ServerStatus` per configured server, including disabled and
        skipped ones.
        """
        if not self._entered:
            raise RuntimeError(
                "GatewayConnections must be used as an async context manager "
                "before connect_all() -- 'async with GatewayConnections(...) as conns:'"
            )

        for cfg in self._configs:
            self._statuses[cfg.id] = await self._connect_one(cfg)

        logger.info(
            "Gateway connected to %d of %d server(s)", self.connected_count, self.total_count
        )
        return self.statuses

    async def _connect_one(self, cfg: ServerConfig) -> ServerStatus:
        status = ServerStatus(server_id=cfg.id, enabled=cfg.enabled)

        if not cfg.enabled:
            status.skipped_reason = "disabled in mcp_servers.yaml"
            logger.warning("Server %r skipped: %s", cfg.id, status.skipped_reason)
            return status

        # Each server gets its own stack so a partial failure unwinds only that
        # server's transport. Ownership moves to the shared stack only on success,
        # which is what keeps one bad server from disturbing the others.
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()

        try:
            read, write, get_session_id = await server_stack.enter_async_context(
                streamablehttp_client(
                    url=cfg.url,
                    timeout=timedelta(seconds=cfg.timeout_seconds),
                )
            )
            session = await server_stack.enter_async_context(
                ClientSession(
                    read,
                    write,
                    read_timeout_seconds=timedelta(seconds=cfg.timeout_seconds),
                    client_info=self._client_info,
                )
            )
            await session.initialize()

            session_id = None
            try:
                session_id = get_session_id()
            except Exception:  # noqa: BLE001 -- diagnostic only, never fatal
                pass
            logger.info(
                "Connected to %r at %s (mcp-session-id=%s)", cfg.id, cfg.url, session_id or "none"
            )

            login_ok = await self._run_session_setup(cfg, session, status)
            if not login_ok:
                # A session that is up but not logged in is the worst outcome:
                # reads work, writes 401 later, mid-crisis. Fail loudly instead.
                await _close_quietly(server_stack)
                return status

            tools_result = await session.list_tools()
            # These servers return their whole tool list in one response; paging
            # (nextCursor) is catalog.py's problem when it needs full entries.
            status.tool_count = len(tools_result.tools)

        # Catching BaseException, not Exception, is load-bearing: a refused
        # connection reaches us as a bare CancelledError from the transport's
        # internal task group, and CancelledError is a BaseException. Catching
        # only Exception here would let one unreachable server crash the gateway.
        except BaseException as exc:  # noqa: BLE001
            unwind_error = await _close_quietly(server_stack)
            # Prefer whatever the unwind surfaced: when the body was merely
            # cancelled, that is where the real failure lives.
            root = unwind_error if (_is_cancellation(exc) and unwind_error) else exc

            if isinstance(exc, (KeyboardInterrupt, SystemExit)) or _is_cancellation(root):
                # Either an interpreter-level exit, or a cancellation with nothing
                # recoverable behind it -- Ctrl-C, or a parent task shutting us
                # down. Swallowing these would make the gateway unkillable.
                raise

            reason = describe_exception(root)
            hint = failure_hint(root, cfg)
            status.connected = False
            status.skipped_reason = reason
            status.error = reason
            logger.warning(
                "Server %r skipped: %s (url=%s)%s",
                cfg.id,
                reason,
                cfg.url,
                f" -- {hint}" if hint else "",
            )
            return status

        # From here the session closes only when the gateway does.
        await self._stack.enter_async_context(server_stack)
        self._sessions[cfg.id] = session
        status.connected = True
        return status

    async def _run_session_setup(
        self,
        cfg: ServerConfig,
        session: ClientSession,
        status: ServerStatus,
    ) -> bool:
        """Runs the configured login, then each post-login step, in order.

        Returns False only when a configured login fails -- that makes the server
        unusable for writes. A failed *setup* step leaves the server connected
        with `setup_ok=False`, because identity still works and only a secondary
        property (the analytics cohort label) is wrong.

        Both are replayable: the same sequence is what a future reconnect must
        re-run, since a restarted server hands back an empty session.
        """
        if cfg.login is not None:
            status.login_attempted = True
            result = await call_tool(session, cfg, cfg.login.tool, cfg.login.args)
            status.login_ok = result.ok

            if not result.ok:
                reason = f"login tool {cfg.login.tool!r} failed: {result.error}"
                status.skipped_reason = reason
                status.error = reason
                logger.warning("Server %r skipped: %s (url=%s)", cfg.id, reason, cfg.url)
                return False

            status.identity = _extract_identity(result.data)
            logger.info(
                "Logged in to %r as %s (identity=%s)",
                cfg.id,
                cfg.login.args.get("name", "<unnamed>"),
                status.identity or "not reported",
            )

        if cfg.post_login_setup:
            status.setup_attempted = True
            for step in cfg.post_login_setup:
                result = await call_tool(session, cfg, step.tool, step.args)
                if not result.ok:
                    message = f"{step.tool}: {result.error}"
                    status.setup_errors.append(message)
                    logger.warning(
                        "Server %r connected, but post-login setup step %s (url=%s)",
                        cfg.id,
                        message,
                        cfg.url,
                    )
            status.setup_ok = not status.setup_errors

        return True

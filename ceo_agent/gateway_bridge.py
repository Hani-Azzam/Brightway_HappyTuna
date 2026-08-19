"""Bridges the async MCP gateway (gateway/) into ToolExecutor's synchronous
tool.run().

Anything that needs the CEO's gateway tools from synchronous agent code wants
these three pieces: GatewayBridge owns the connection lifetime,
GatewayToolAdapter exposes one gateway tool as a ToolBase, and
setup_gateway_tools/teardown_gateway_tools wire the whole set into a
ToolExecutor.
"""
import asyncio
import threading

from base.tool_base import ToolBase, ToolResult, ToolSchema
from gateway.catalog import build_catalog
from gateway.connection import GatewayConnections
from gateway.registry import load_registry
from gateway.router import Router
from services.tool_executor import ToolExecutor


class GatewayBridge:
    """Owns the gateway's whole connection lifetime on one background-thread
    event loop, and lets synchronous code (GatewayToolAdapter.run) call into
    it.

    Naive version tried, and why it broke: dispatch every gateway coroutine
    -- __aenter__, connect_all(), each tool call, __aexit__ -- individually
    via `asyncio.run_coroutine_threadsafe(coro, loop)`. That runs each one as
    its OWN asyncio Task, even though they all share the same loop. MCP's
    streamable-http transport opens an anyio task group inside
    GatewayConnections.__aenter__ (one per server) and anyio ties a task
    group's cancel scope to the specific Task that entered it; closing it
    from a different Task -- which is exactly what a separate __aexit__
    submission is -- raises "Attempted to exit cancel scope in a different
    task than it was entered in".

    Fix: __aenter__, connect_all() and __aexit__ all run inside ONE
    coroutine (`_lifecycle`), submitted once, so they share a Task. Between
    connecting and closing, that task blocks on an asyncio.Event; individual
    tool calls are dispatched with their own `run_coroutine_threadsafe` calls
    same as before, which is safe -- a plain `session.call_tool()` doesn't
    open or close the connections' task groups, so it doesn't care which
    Task it runs on.
    """

    def __init__(self, role: str, dry_run: bool) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self._ready = threading.Event()
        self._closed = threading.Event()
        self._setup_error: BaseException | None = None
        self.statuses: list = []
        self.router: Router | None = None

        asyncio.run_coroutine_threadsafe(self._lifecycle(role, dry_run), self.loop)
        self._ready.wait()
        if self._setup_error is not None:
            self._stop_thread()
            raise self._setup_error

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _lifecycle(self, role: str, dry_run: bool) -> None:
        self._shutdown_event = asyncio.Event()
        try:
            configs = load_registry(profile="local")
            async with GatewayConnections(configs) as connections:
                await connections.connect_all()
                self.statuses = connections.statuses
                catalog = await build_catalog(connections.sessions)
                self.router = Router(connections, catalog, role=role, dry_run=dry_run)
                self._ready.set()
                await self._shutdown_event.wait()
        except Exception as exc:  # noqa: BLE001 -- surfaced to the main thread, not swallowed
            self._setup_error = exc
            self._ready.set()
        finally:
            self._closed.set()

    def call(self, coro):
        """Runs one gateway coroutine (e.g. `router.call_tool(...)`) on the
        background loop and blocks for its result. Safe to call from any
        thread and interleaved freely with other calls -- see class
        docstring for why this is safe but bracketing connect/close was not.
        """
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self.loop.call_soon_threadsafe(self._shutdown_event.set)
        self._closed.wait(timeout=10)
        self._stop_thread()

    def _stop_thread(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
        self.loop.close()


class GatewayToolAdapter(ToolBase):
    """Wraps one gateway-catalog tool (e.g. "support.patch_ticket") as a
    ToolBase, so ToolExecutor can register and call it exactly like
    Check_Inbox or Send_Email. All the policy/identity/dry-run/audit work
    still happens inside Router.call_tool -- this only adapts sync <-> async.
    """

    def __init__(
        self,
        bridge: GatewayBridge,
        qualified_name: str,
        description: str,
        input_schema: dict,
        is_read: bool,
    ) -> None:
        self._bridge = bridge
        self._qualified_name = qualified_name
        self._is_read = is_read
        self._schema = ToolSchema(
            name=qualified_name,
            description=description or qualified_name,
            parameters=input_schema or {"type": "object", "properties": {}},
        )

    @property
    def schema(self) -> ToolSchema:
        return self._schema

    def run(self, **kwargs) -> ToolResult:
        result = self._bridge.call(self._bridge.router.call_tool(self._qualified_name, kwargs))
        # Reads are safe to retry; writes (support.patch_ticket, social.*)
        # are not -- a retried write could double-fire a side effect.
        if result.ok:
            value = result.data if result.data is not None else result.text
            return ToolResult(value=value, is_idempotent=self._is_read)
        return ToolResult(error=result.error, is_idempotent=self._is_read)


def setup_gateway_tools(executor: ToolExecutor, role: str, dry_run: bool) -> GatewayBridge:
    """Connects to the MCP gateway and registers every tool `role` may call.

    `--profile local` (mirrored here via profile="local"): this script runs
    on the host, not inside the compose network, so it needs the
    host-published ports from docker-compose.yml.

    Never silently loses a server: connect_all() already records a reason
    for each server that did not connect (README: "A silent CEO and one that
    couldn't reach the platform must not look alike"), surfaced below before
    any tool is registered. GatewayBridge cleans up its own thread if
    anything in setup fails (e.g. CatalogError for an unclassified tool) and
    re-raises, so a genuine setup bug is never swallowed.
    """
    bridge = GatewayBridge(role=role, dry_run=dry_run)

    print("=== Gateway connection status ===")
    for status in bridge.statuses:
        if status.connected:
            print(f"  ok      {status.server_id:<10} {status.tool_count} tools")
        else:
            print(f"  SKIPPED {status.server_id:<10} {status.skipped_reason}")

    access_by_name = {entry.qualified_name: entry.access for entry in bridge.router.get_tools()}
    registered = 0
    for spec in bridge.router.get_tools_for_llm():
        qualified_name = spec["name"]
        executor.register(GatewayToolAdapter(
            bridge=bridge,
            qualified_name=qualified_name,
            description=spec["description"],
            input_schema=spec["input_schema"],
            is_read=access_by_name.get(qualified_name) == "read",
        ))
        registered += 1

    print(f"=== Registered {registered} gateway tool(s) for role {role!r} "
          f"(dry_run={dry_run}) ===\n")
    return bridge


def teardown_gateway_tools(bridge: GatewayBridge) -> None:
    bridge.close()

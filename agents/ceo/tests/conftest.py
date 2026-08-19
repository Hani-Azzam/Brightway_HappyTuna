"""Shared fixtures.

The important one is `gateway`: it connects once per session and, if nothing is
reachable, skips the integration tests with an instruction instead of letting a
wall of connection errors out. Unit tests never touch it.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Makes `import gateway` work when pytest is run from the repo root.
CEO_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CEO_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CEO_AGENT_DIR))

from gateway.catalog import build_catalog  # noqa: E402
from gateway.connection import GatewayConnections  # noqa: E402
from gateway.registry import RegistryError, load_registry  # noqa: E402

SERVERS_DOWN = (
    "MCP servers are not reachable.\n"
    "        Start them:  docker compose up -d social-network customer-support-mcp\n"
    "        Then re-run: pytest ceo_agent/tests/test_integration.py\n"
    "        (tests use the 'local' profile by default; inside the compose network\n"
    "         pass --profile docker)"
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--profile",
        action="store",
        default=None,
        choices=("docker", "local"),
        help="URL profile for integration tests. Overrides GATEWAY_URL_PROFILE and pytest.ini.",
    )
    parser.addini(
        "gateway_profile",
        "Default URL profile for integration tests when neither --profile nor "
        "GATEWAY_URL_PROFILE is set.",
        default="local",
    )


@pytest.fixture(scope="session")
def profile(pytestconfig: pytest.Config) -> str:
    """--profile, then GATEWAY_URL_PROFILE, then pytest.ini's gateway_profile."""
    from_cli = pytestconfig.getoption("--profile")
    if from_cli:
        return str(from_cli)
    from_env = os.environ.get("GATEWAY_URL_PROFILE", "").strip()
    if from_env:
        return from_env
    return str(pytestconfig.getini("gateway_profile") or "local")


class Gateway:
    """What an integration test needs: live connections plus the built catalog."""

    def __init__(self, connections: GatewayConnections, catalog) -> None:
        self.connections = connections
        self.catalog = catalog

    @property
    def statuses(self):
        return self.connections.statuses


@pytest.fixture(scope="session")
async def gateway(profile: str):
    """One set of live connections for the whole session.

    Skips -- rather than fails -- when nothing is reachable, so a run with Docker
    down reports "skipped, start the servers" instead of a stack of transport
    errors. Partial connectivity is *not* skipped: that is a real problem, and
    test_all_servers_connect is meant to fail on it.

    The connections are opened and closed inside one dedicated task. They cannot
    simply be held across a `yield` here: the MCP transports run on anyio cancel
    scopes, which must be exited by the same task that entered them, and pytest
    runs setup and teardown in different tasks. Without the owner task, session
    teardown fails with "Attempted to exit cancel scope in a different task".
    """
    try:
        configs = load_registry(profile=profile)
    except RegistryError as exc:
        pytest.skip(f"Registry could not be loaded: {exc}")

    ready = asyncio.Event()
    stop = asyncio.Event()
    state: dict[str, object] = {}

    async def owner() -> None:
        try:
            async with GatewayConnections(configs) as connections:
                await connections.connect_all()
                if connections.connected_count == 0:
                    state["skip"] = SERVERS_DOWN
                else:
                    state["gateway"] = Gateway(
                        connections, await build_catalog(connections.sessions)
                    )
                ready.set()
                await stop.wait()
        finally:
            # So a failure before the yield cannot deadlock the fixture.
            ready.set()

    task = asyncio.create_task(owner())
    await ready.wait()

    if task.done():
        task.result()  # Re-raises whatever went wrong, e.g. CatalogError.

    if "skip" in state:
        stop.set()
        await task
        pytest.skip(str(state["skip"]))

    try:
        yield state["gateway"]
    finally:
        stop.set()
        await task

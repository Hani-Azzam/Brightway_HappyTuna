"""
Entrypoint for the customer-agent container. Runs two things:

1. `nat mcp serve` -- exposes customer_agent_react as an MCP tool for
   on-demand external callers (see README.md's "Calling it directly").
   Still useful even though nothing currently calls it automatically
   (ceo_agent's registry doesn't include it yet) -- it's how this was
   tested end-to-end, and how any future caller would reach it.
2. driver.py's run() -- subscribes to the event generator and reacts to
   crisis events on its own, once per persona. This is the piece that
   makes the agent autonomous instead of purely on-demand.

Mirrors influencer-agent/src/influencer_agent/main.py's shape: the NAT
front end runs as a subprocess, the driving loop runs in this process.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import driver

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("customer_agent.main")


async def _run_nat_mcp_serve(host: str, port: int) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "nat", "mcp", "serve",
        "--config_file", "workflow.yml",
        "--host", host,
        "--port", str(port),
        "--tool_names", "customer_agent_react",
    )


async def _amain() -> None:
    host = os.environ.get("NAT_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("NAT_MCP_PORT", "8000"))

    logger.info("Starting nat mcp serve on %s:%d", host, port)
    nat_process = await _run_nat_mcp_serve(host, port)

    async def shutdown() -> None:
        if nat_process.returncode is None:
            nat_process.terminate()
            try:
                await asyncio.wait_for(nat_process.wait(), timeout=10)
            except asyncio.TimeoutError:
                nat_process.kill()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))
        except NotImplementedError:
            pass  # Windows local dev; only matters for container shutdown

    try:
        logger.info("Starting event-generator driver...")
        await driver.run()
    finally:
        await shutdown()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

"""Entrypoint for the influencer-agent container.

Runs two things in one process group:
1. `nat serve` — the NAT workflow (configs/config.*.yml).
2. The poller (poller.py) — polls social_network, calls the NAT workflow, acts on its
   decision. This is the process that actually talks to social_network's HTTP API.

`nat serve` binds to 0.0.0.0 so Docker's published port (8002:8000 in docker-compose.yml)
can reach it from the host — useful for exercising the workflow directly via Swagger at
/docs without going through social_network at all. A 127.0.0.1-only bind would be invisible
to Docker's port-forwarding even though the container-internal poller could still reach it,
which is a common trap: "the poller works" does not mean "the published port works". This
does mean the raw decision endpoint is reachable by anyone who can reach this container's
published port, with no auth in front of it — acceptable here since the whole platform's
auth model is already "no real security, name-only tokens" (see social_network/CLAUDE.md).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from .nat_client import NatWorkflowClient
from .persona import load_persona_instance, render_persona_prompt
from .poller import InfluencerPoller
from .social_client import SocialNetworkClient
from .state import PersonaCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("influencer_agent.main")

APP_ROOT = Path(__file__).resolve().parents[2]  # influencer-agent/


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


async def _run_nat_serve(config_file: Path, host: str, port: int) -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        "nat",
        "serve",
        "--config_file",
        str(config_file),
        "--host",
        host,
        "--port",
        str(port),
    )
    return process


async def _amain() -> None:
    nat_config_file = APP_ROOT / _env("NAT_CONFIG_FILE", "configs/config.nim.yml")
    nat_bind_host = "0.0.0.0"  # so Docker's published port can reach it — see module docstring
    nat_client_host = "127.0.0.1"  # loopback: how *this* container's own poller reaches it
    nat_port = int(_env("NAT_SERVE_PORT", "8000"))

    base_persona_template_path = Path(_env("BASE_PERSONA_TEMPLATE_PATH", "/app/docs/influencer_persona_prompt.md"))
    persona_file = APP_ROOT / "personas" / _env("PERSONA_FILE", "brand_supporter.yaml")
    state_dir = Path(_env("STATE_DIR", "/app/state"))

    social_network_base_url = _env("SOCIAL_NETWORK_BASE_URL", "http://localhost:3000")
    company_name = _env("COMPANY_NAME", "HappyTuna")
    poll_interval_seconds = float(_env("POLL_INTERVAL_SECONDS", "30"))
    feed_page_size = int(_env("FEED_PAGE_SIZE", "20"))

    logger.info("Starting NAT workflow server (%s) on %s:%d", nat_config_file.name, nat_bind_host, nat_port)
    nat_process = await _run_nat_serve(nat_config_file, nat_bind_host, nat_port)

    nat_client = NatWorkflowClient(base_url=f"http://{nat_client_host}:{nat_port}")
    social_client = SocialNetworkClient(base_url=social_network_base_url)

    async def shutdown() -> None:
        await nat_client.aclose()
        await social_client.aclose()
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
            pass  # Windows' event loop doesn't support add_signal_handler; fine for local dev.

    try:
        logger.info("Waiting for NAT workflow server to become ready...")
        await nat_client.wait_until_ready(attempts=30, delay_seconds=2.0)

        persona = load_persona_instance(persona_file)
        persona_prompt = render_persona_prompt(base_persona_template_path, persona, company_name)
        logger.info("Loaded persona %s (@%s) from %s", persona.name, persona.handle, persona_file.name)

        cursor = PersonaCursor(state_dir=state_dir, persona_handle=persona.handle)

        poller = InfluencerPoller(
            social_client=social_client,
            nat_client=nat_client,
            cursor=cursor,
            persona=persona,
            persona_prompt=persona_prompt,
            company_name=company_name,
            feed_page_size=feed_page_size,
            poll_interval_seconds=poll_interval_seconds,
        )
        await poller.start()
    finally:
        await shutdown()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()

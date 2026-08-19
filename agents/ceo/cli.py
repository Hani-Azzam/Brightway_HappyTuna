#!/usr/bin/env python3
"""The gateway's one entry point. Two subcommands, both read-only.

    python ceo_agent/cli.py check --profile local
    python ceo_agent/cli.py dump  --profile local [--all] [--json]

`check` connects and prints one line per server plus a catalog/policy summary.
`dump` prints the CEO's tool surface exactly as the model receives it.

This prints; it does not verify. Verification lives in ceo_agent/tests/ --
`pytest ceo_agent/tests/test_integration.py` asserts the things this only shows.
Neither subcommand writes anything: no tickets, no posts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Lets this run from a checkout without installing the package.
CEO_AGENT_DIR = Path(__file__).resolve().parent
if str(CEO_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CEO_AGENT_DIR))

from gateway.catalog import Catalog, CatalogError, build_catalog  # noqa: E402
from gateway.connection import GatewayConnections  # noqa: E402
from gateway.policy import Policy, PolicyError, build_policy  # noqa: E402
from gateway.registry import RegistryError, load_registry  # noqa: E402
from gateway.router import Router, prepare_schema, to_langchain_name  # noqa: E402

RULE = "=" * 78


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


async def cmd_check(profile: str | None, role: str) -> int:
    """Connect, catalogue, apply the policy, and summarise. Exit 0 if all is well."""
    configs = load_registry(profile=profile)

    async with GatewayConnections(configs) as connections:
        await connections.connect_all()

        print(RULE)
        print("SERVERS")
        print(RULE)
        for status in connections.statuses:
            if status.connected:
                bits = [f"{status.tool_count} tools"]
                if status.login_ok is not None:
                    bits.append(f"login {'ok' if status.login_ok else 'FAILED'}")
                if status.identity:
                    bits.append(f"identity={status.identity}")
                if status.setup_ok is False:
                    bits.append(f"setup FAILED ({'; '.join(status.setup_errors)})")
                print(f"  ok      {status.server_id:<12} {', '.join(bits)}")
            else:
                print(f"  SKIPPED {status.server_id:<12} {status.skipped_reason}")

        connected = connections.connected_count
        total = connections.total_count
        print(f"\n  {connected}/{total} connected")

        if connected == 0:
            print("\nNothing reachable. Start the services and use the local profile:")
            print("  docker compose up -d social-network customer-support-mcp")
            print("  python ceo_agent/cli.py check --profile local")
            return 1

        # Catalog. An unclassified tool stops here, by design.
        try:
            catalog = await build_catalog(connections.sessions)
        except CatalogError as exc:
            print(f"\n{RULE}\nCATALOG ERROR\n{RULE}\n{exc}")
            return 1

        counts = catalog.access_counts()
        print(f"\n{RULE}\nCATALOG\n{RULE}")
        print(f"  {len(catalog)} tools across {len(catalog.server_ids)} servers"
              f" -- {counts['read']} read, {counts['write']} write,"
              f" {counts['public_write']} public_write")
        for server_id in catalog.server_ids:
            print(f"    {server_id:<12} {len(catalog.for_server(server_id))}")

        # Policy.
        try:
            policy = build_policy(role)
        except PolicyError as exc:
            print(f"\n{RULE}\nPOLICY ERROR\n{RULE}\n{exc}")
            return 1

        visible = policy.visible_tools(catalog)
        hidden = len(catalog) - len(visible)
        print(f"\n{RULE}\nPOLICY -- role {role!r}\n{RULE}")
        print(f"  {len(visible)} visible, {hidden} hidden")
        for server_id in catalog.server_ids:
            shown = [e for e in visible if e.server_id == server_id]
            total_here = len(catalog.for_server(server_id))
            tags = sorted({e.access for e in shown})
            print(f"    {server_id:<12} {len(shown):>2} of {total_here:>2}"
                  f"   {', '.join(tags) if tags else '-'}")

        writes = [e for e in visible if e.access != "read"]
        if writes:
            print("\n  writes available to this role:")
            for entry in writes:
                print(f"    [{entry.access}] {entry.qualified_name}")

        problems = policy.validate_against_catalog(catalog)
        if problems:
            print(f"\n{RULE}\nDEAD RULES -- these match nothing in the live catalog\n{RULE}")
            for problem in problems:
                print(f"  {problem}")
            print("\n  Usually an upstream rename. Not fatal: under default-deny a rule")
            print("  matching nothing grants nothing and revokes nothing.")

        if connected < total:
            print(f"\n  {total - connected} server(s) did not connect -- surface is incomplete.")
            return 1
        return 0


# ---------------------------------------------------------------------------
# dump
# ---------------------------------------------------------------------------


def _surface(router: Router, catalog: Catalog, policy: Policy) -> dict[str, Any]:
    """The visible surface, plus what was hidden and why, as plain data."""
    visible = []
    for spec, entry in zip(router.get_tools_for_llm(), router.get_tools()):
        visible.append({
            "qualified_name": entry.qualified_name,
            "langchain_name": to_langchain_name(entry.qualified_name),
            "server_id": entry.server_id,
            "access": entry.access,
            "description": spec["description"],
            "input_schema": spec["input_schema"],
        })

    hidden = []
    for entry in catalog:
        decision = policy.decide(entry.qualified_name)
        if not decision.allowed:
            hidden.append({
                "qualified_name": entry.qualified_name,
                "server_id": entry.server_id,
                "access": entry.access,
                "reason": decision.reason,
                "matched_rule": decision.matched_rule,
            })

    return {
        "role": router.role_id,
        "catalogued": len(catalog),
        "visible": visible,
        "hidden": hidden,
    }


async def cmd_dump(profile: str | None, role: str, show_all: bool, as_json: bool) -> int:
    configs = load_registry(profile=profile)

    async with GatewayConnections(configs) as connections:
        await connections.connect_all()
        if connections.connected_count == 0:
            print("Nothing reachable. Start the services and use the local profile:",
                  file=sys.stderr)
            print("  docker compose up -d social-network customer-support-mcp", file=sys.stderr)
            return 1

        catalog = await build_catalog(connections.sessions)
        policy = build_policy(role)
        router = Router(connections, catalog, role=role)
        surface = _surface(router, catalog, policy)

        if as_json:
            print(json.dumps(surface, indent=2, sort_keys=True))
            return 0

        print(RULE)
        print(f"CEO GATEWAY TOOL SURFACE -- role: {role}")
        print(RULE)
        print(f"  {len(surface['visible'])} visible of {surface['catalogued']} catalogued "
              f"({len(surface['hidden'])} hidden)")
        print("  Schemas below are post-injection: gateway-filled params removed,")
        print("  Customer Support enums added. This is what the model sees.")

        for server_id in catalog.server_ids:
            tools = [t for t in surface["visible"] if t["server_id"] == server_id]
            if not tools:
                continue
            print(f"\n{RULE}\nSERVER: {server_id}  --  {len(tools)} visible / "
                  f"{len(catalog.for_server(server_id))} total\n{RULE}")
            for tool in tools:
                print(f"\n[{tool['access']}] {tool['qualified_name']}")
                print(f"    langchain name : {tool['langchain_name']}")
                print(f"    description    : {(tool['description'] or '').strip()}")
                print("    input_schema   :")
                for line in json.dumps(tool["input_schema"], indent=2, sort_keys=True).splitlines():
                    print(f"      {line}")

        if show_all and surface["hidden"]:
            print(f"\n{RULE}\nHIDDEN -- {len(surface['hidden'])} tools, and the rule that hid each\n{RULE}")
            for tool in surface["hidden"]:
                rule = tool["matched_rule"] or "no matching rule"
                print(f"  [{tool['access']:<12}] {tool['qualified_name']:<40}"
                      f" {tool['reason']} ({rule})")

        return 0


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Inspect the CEO agent's MCP gateway. Read-only.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", choices=("docker", "local"),
                        help="Which URL set to use (default: mcp_servers.yaml's).")
    common.add_argument("--role", default="ceo", help="Role id from roles.yaml (default: ceo).")
    common.add_argument("-v", "--verbose", action="store_true", help="Show INFO logs.")

    sub.add_parser("check", parents=[common],
                   help="Connect, catalogue, summarise the policy. Exit 0 if healthy.")

    dump = sub.add_parser("dump", parents=[common],
                          help="Print the role's tool surface with prepared schemas.")
    dump.add_argument("--all", action="store_true", dest="show_all",
                      help="Also list hidden tools and the rule that hid each.")
    dump.add_argument("--json", action="store_true", dest="as_json",
                      help="Machine-readable output, for diffing a roles.yaml change.")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.ERROR)

    try:
        if args.command == "check":
            return asyncio.run(cmd_check(args.profile, args.role))
        return asyncio.run(cmd_dump(args.profile, args.role, args.show_all, args.as_json))
    except RegistryError as exc:
        print(f"Registry error: {exc}", file=sys.stderr)
        return 2
    except PolicyError as exc:
        print(f"Policy error: {exc}", file=sys.stderr)
        return 2
    except CatalogError as exc:
        print(f"Catalog error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

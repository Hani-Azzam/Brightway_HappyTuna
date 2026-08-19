# CEO Agent — MCP Gateway

Connects to the four MCP servers the other teams run (Customer Support, Social
Network, Social Analytics, Internal Chat) and exposes a filtered tool set per
role. It injects the caller's identity server-side, holds back every write in dry
run, and audits every call. It makes no decisions — the loop, prompts, and model
are yours.

## Setup

```bash
# macOS ships python3, not python
cp social_network/.env.example social_network/.env      # compose fails without it

# The chat server lives in the bitrix-internal-actors stack, not this one. Bring
# it up first: our compose joins its network as external, and a missing external
# network is a hard compose failure, not a warning.
docker compose -f ../bitrix-internal-actors/docker-compose.yml up -d
docker compose up -d social-network customer-support-mcp

python3 -m venv .venv && source .venv/bin/activate
pip install -r ceo_agent/requirements.txt

pytest                                          # 62 passed, 4 deselected
python3 ceo_agent/cli.py check --profile local  # 4/4 connected, 30 visible
```

`Customer_Support_System/requirements.txt` must pin `mcp==1.29.0`. Unpinned, pip
installs 2.0.0 and their container crashes on startup.

## Usage

```python
from gateway.catalog import build_catalog
from gateway.connection import GatewayConnections
from gateway.registry import load_registry
from gateway.router import Router

async with GatewayConnections(load_registry(profile="local")) as connections:
    await connections.connect_all()
    catalog = await build_catalog(connections.sessions)
    router = Router(connections, catalog, role="ceo", dry_run=True)

    # A silent CEO and one that couldn't reach the platform must not look alike.
    for status in router.get_status():
        if not status.connected:
            print(status.server_id, status.skipped_reason)
    tools = router.get_langchain_tools()   # StructuredTools, filtered to the role
    agent = create_agent(model, tools, system_prompt=YOUR_BRIEF)

    result = await router.call_tool("support.patch_ticket", {
        "ticket_id": "TCK-00042", "status": "escalated",
    })
```

`dry_run=True` answers **every write** without sending it — public posts, ticket
patches and chat alike; reads still execute, so the agent sees real data and
changes nothing. Keep it on until the agent should act for real.
Your brief needs no tool list — the model reads the schemas. `Router` never raises:
check `result.ok`. `langchain`/`langgraph` are not dependencies of this package.

## What the CEO can do

30 of 48 tools are visible to role `ceo`: the support queue, the analytics
surface, public reads, and the internal chat. Six of them write:

| Tool | |
|---|---|
| `social.create_post` | **irreversible, public** — no delete tool exists anywhere |
| `social.add_comment` | **irreversible, public** — joins a thread, inherits its audience |
| `support.patch_ticket` | respond, escalate, reassign |
| `chat.send_message` | internal — speaks in a channel the org already has |
| `chat.create_channel` | internal, **permanent** — no `delete_channel` anywhere |
| `chat.add_member` | internal, **permanent** — no `remove_member` anywhere |

The chat writes are classified `write`, not `public_write`: they land in the
company's own chat, absent from every analytics number and invisible to the
simulated public. The distinction in `TOOL_ACCESS` is blast radius, not
reversibility — and by that measure they are irreversible too, hence the gotchas
below.

Hidden: `run_analysis` and `set_ai_analysis` (they mutate the numbers the CEO is
scored against), `social.login`, `social.set_account_type` and `chat.login`
(identity — connection.py runs the logins itself, the model never sees them), and
`support.create_ticket` (fabricating a complaint). Chat is granted tool by tool
rather than as `chat.*`, so anything that team ships later stays hidden until
someone decides otherwise. `customer-agent` is not in the registry at all — its
one tool invents a customer *and* files a real ticket.

## Adding an MCP server

Three edits, no code:

1. a block in `mcp_servers.yaml`
2. its tools classified in `TOOL_ACCESS` (`gateway/catalog.py`)
3. a grant in `roles.yaml`

```yaml
  - id: email
    urls:
      docker: http://email-service:8020/mcp
      local: http://localhost:8020/mcp
```

If the server binds identity to the session — as `social` and `chat` both do,
throwing 401 until it runs — add a `login` block too. `connection.py` owns it and
replays it after every reconnect, so its arguments must be idempotent and stable
for the whole simulation, and the tool itself belongs in `deny`.

A live tool missing from `TOOL_ACCESS` aborts the catalog build, on purpose — an
unassessed capability must not reach the agent by default. Forgetting to *grant*
one just leaves it hidden. Update `RECORDED_*` in `tests/test_integration.py`.

## Commands

```bash
python3 ceo_agent/cli.py check --profile local       # connect, catalogue, policy summary
python3 ceo_agent/cli.py dump  --profile local       # the surface, as the model sees it (--all, --json)
pytest ceo_agent/tests/test_unit.py                  # no network, no Docker
pytest ceo_agent/tests/test_integration.py           # needs the servers; skips cleanly if down
pytest -m smoke -s                                   # call all 24 read tools once, print the table
```

## Gotchas

- `--profile local` is required off-compose; the default `docker` profile uses
  compose hostnames that don't resolve from your host.
- `pytest -m writes` creates and patches a real ticket, and creates a chat channel
  and message. Off by default.
- Dry run holds back **every write**, `write` and `public_write` alike; reads still
  execute, so the agent sees real data and changes nothing. It gates on
  `access != "read"`, so a new access level is withheld until someone decides
  otherwise. It gated `public_write` only until chat arrived and made a dry run
  able to open a channel with no delete tool — if you are cherry-picking across
  that change, note that `support.patch_ticket` used to execute under dry run.
- Chat state accretes and cannot be cleaned up from the tool surface: the server
  exposes no `delete_channel` and no `remove_member`, so every `create_channel` and
  `add_member` is permanent. Same shape of problem as the ticket rows above, on a
  different server — but worse, because the CEO can reach these itself rather than
  only the harness. Reset the `bitrix-internal-actors` stack between trials, or
  trial N starts with N-1 incident channels left over.
- A whole-server allow (`analytics.*`) sweeps in that server's writes. The explicit
  `deny` entries in `roles.yaml` are load-bearing — deleting one silently grants
  operator powers.
- `streamablehttp_client` is deprecated in mcp 1.29.0 and gone in 2.0. Migrating
  means owning an `httpx.AsyncClient` to keep per-server timeouts.
- `ENUM_INJECTIONS` in `router.py` hand-copies
  `Customer_Support_System/models.py:7-34`; nothing fails if they add a member.

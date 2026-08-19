# Internal Messaging System (Internal Chat)

A standalone **business-system surface** agents talk *through* — no LLM, no
reasoning. Channels + messages + membership + trust labels, reachable over the
wire three ways. Design notes: [`DESIGN.md`](../../DESIGN.md).

## The three doors

| Door | Who uses it | How |
|---|---|---|
| **Standard MCP** (`mcp_server.py`, streamable-http on :8090) | The CEO gateway, or any real-MCP client | `login(agent_id)` binds identity to the MCP session, then `list_channels` / `read_channel` / `send_message` / `create_channel` / `add_member` |
| **REST** (`transport/rest`, :8080) | Employee agents, scripts, curl | `Authorization: Bearer <agent_id>`; `/api/channels…` |
| **Bespoke tool envelope** (`/mcp/chat/tools` + `/mcp/chat/call`) | `mcp_core`-style clients (`HttpMCPClient`) | identity = Bearer header; raw `ToolResult` envelope |

All three delegate to the same `InternalMessagingService`, so membership authz,
channel rules, and trust labels live in exactly one place. Identity is always
bound at the connection/session layer — never a tool argument — so an agent
cannot impersonate another by crafting args.

At startup the MCP container idempotently seeds a standing incident channel
(`ht-crisis`, CEO-1 + all employee ids); disable with `CHAT_SEED=false`.

## Layout

```
app/         config + FastAPI factory (create_app) + build_service
domain/      models · store (SQLite/Postgres) · service (rules + authz)
integration/ clock · ids · identity (Registry) · events (publisher seam) · cache
transport/   mcp/tools.py (chat.* BaseTools) · rest/app.py (REST + envelope)
mcp_server.py  the standard MCP door (FastMCP, streamable-http)
tests/       store · service (isolation/trust) · mcp · rest · reproducibility
```

## Backends (pluggable, chosen by env)

| Concern | Env | Default | Optional |
|---|---|---|---|
| Durable state | `CHAT_STORE` | `sqlite` (`CHAT_DB_PATH`) | `postgres` (`CHAT_DB_URL`) |
| Active state | `CHAT_CACHE` | `none` | `redis` (roster cache + unread counters) |
| Events | `CHAT_BUS` | `none` | `kafka` / `redis` (`chat.message_posted`) |

Defaults are the zero-infra path (what the unified compose uses); the optional
drivers are imported lazily and are not installed in the default image — see
`requirements.txt`. Full integration recipes: [`INTEGRATION.md`](INTEGRATION.md).

## Run

Part of the unified compose at the repo root (two containers sharing one SQLite
volume, same pattern as the customer-support platform):

```bash
docker compose up -d internal-chat internal-chat-mcp
# REST on http://localhost:8085, MCP on http://localhost:8090/mcp
```

Local dev without Docker:

```bash
# tests (SQLite + fakes, no infra)
python -m pytest services/internal_messaging/tests -q
# REST door
python -m uvicorn services.internal_messaging.app.main:app --port 8085
# standard MCP door
MCP_PORT=8090 python -m services.internal_messaging.mcp_server
```

`CHAT_DB_PATH` overrides the SQLite location. For a replayable run, build the
service with `FixedClock` + `SeededIdFactory` (see `app/main.build_service`).

# Internal Messaging System (Internal Chat)

A standalone BitriX **business-system surface** agents talk *through* — no LLM, no
reasoning. Channels + messages + membership + trust labels, reachable over the wire
via **MCP (`chat.*`)** and **REST**. Design: [`docs/internal_chat_v2_design.md`](../../docs/internal_chat_v2_design.md).

Built strictly on the COO `mcp_core` contract, the KB/roles/tools docs, and the
social-network surface pattern. It reuses **no** prior internal-chat code.

## Status

| Phase | What | State |
|---|---|---|
| P0 | store + models + injected clock/ids (own SQLite, append-only log) | ✅ |
| P1 | service: membership authz, trust labels, channel rules, event seam | ✅ |
| P2 | MCP `chat.*` tools (`mcp_core.BaseTool`) — matches COO's `chat.send_message` | ✅ |
| P3 | REST face + **employee agentkit adapter** (`services/employee/tools/internal_messaging_adapter.py`) | ✅ |
| P4 | event bus: `BusPublisher` fans `chat.message_posted` to per-recipient Redis Streams (`chat.inbox.<agent>`) + a global stream; `InMemoryBus` for tests | ✅ |
| P5 | `Dockerfile` + compose service (`internal-messaging`); `NtpClock` world-clock seam (`NTP_URL`) | ✅ |
| P6 | full production stack (KB §2.3): **PostgreSQL** durable state (`PostgresStore`, seq from a shared DB sequence), **Redis** active state (roster cache + unread counters), **Kafka** events (`KafkaPublisher`, channel-keyed topic) — all pluggable behind zero-infra defaults | ✅ |

> P4/P5 verified by tests + `docker-compose config`. Image build not run here (no Docker in the dev
> sandbox); the app is confirmed serving under uvicorn via the FastAPI TestClient.

## Layout

```
app/         config + FastAPI factory (create_app) + build_service
domain/      models · store (SQLite) · service (rules + authz)
integration/ clock (Wall|Fixed) · ids (Uuid|Seeded) · identity (Registry) · events (publisher seam)
transport/   mcp/tools.py (chat.* BaseTools) · rest/app.py (REST + envelope)
tests/       store · service (isolation/trust) · mcp · rest · employee adapter · reproducibility
```

## Who talks how — every agent as its own service, over the wire

- **COO / CEO** (`mcp_core`): **remote MCP door** — `HttpMCPClient(http, agent_id, base_url)` from
  `packages.mcp_core.http_client` → `GET /mcp/chat/tools`, `POST /mcp/chat/call`. Same `MCPClient`
  contract as in-process; identity is the bound `agent_id` (Bearer). No tool-code change.
- **Employee** (`agentkit`): REST door via `SendChatMessage`/`ReadChannel` adapter; identity bound as
  `Bearer <employee_id>`, writes `is_idempotent=False`.
- **Cross-language / Director**: REST (`/api/channels…`, `?since=`) + `chat.message_posted` events.

`LocalMCPClient` (`build_chat_client`) remains for in-process/tests. Over the wire, `value` arrives as a
dict inside the `ToolResult` envelope — callers may revalidate with the schema (e.g. `MessageReceipt`)
for typed access.

## Backends (pluggable, chosen by env)

| Concern | Env | Local default | Production |
|---|---|---|---|
| Durable state | `CHAT_STORE` | `sqlite` | `postgres` (`PostgresStore`, `CHAT_DB_URL`) |
| Active state | `CHAT_CACHE` | `none` | `redis` (roster cache + unread counters) |
| Events | `CHAT_BUS` | `none` | `kafka` (`chat.message_posted`, channel-keyed) |

Defaults are the zero-infra path so the test suite runs with nothing running; drivers
(`psycopg`, `redis`, `confluent_kafka`) are imported lazily only when their backend is
selected. Full env matrix + integration recipes: [`INTEGRATION.md`](INTEGRATION.md).

## Run

```bash
# tests (SQLite + fakes, no infra)
.venv/Scripts/python.exe -m pytest services/internal_messaging/tests -q
# serve REST + MCP (dev, SQLite)
.venv/Scripts/python.exe -m uvicorn services.internal_messaging.app.main:app --port 8085
# full stack (Postgres + Redis + Kafka)
docker compose up internal-messaging
```

`CHAT_DB_PATH` overrides the SQLite location. For a replayable run, build the service with
`FixedClock` + `SeededIdFactory` (see `app/main.build_service`).

## Prerequisite note

`packages/mcp_core` and the chat payloads in `packages/schemas/tool_results.py` were brought over from
the `COO-Agent` branch to land the shared contract here (they were stubs/partial on this branch). When
that branch merges, these are the same files — additive, no divergence.

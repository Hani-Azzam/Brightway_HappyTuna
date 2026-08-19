# Internal Messaging System — Integration Guide

For any team that wants to plug an agent or system into the **Internal Messaging System**
(the BitriX "Internal Chat"). It is a **business-system surface**: it stores channels,
messages, and membership, labels content with a trust level, and emits one event per
change. **No LLM, no reasoning.** Agents talk *through* it; it never talks back.

- **Two doors, one process, one port:** REST (`/api/*`) and MCP (`/mcp/chat`).
- **Own database** (SQLite). Independently deployable; reach it over the network.
- **Envelope:** REST returns `{ "success": true, "data": … }` or `{ "success": false, "error": {code,message} }`.

---

## The one rule you must understand

**Your identity is the connection, never a field in the request body.**
- REST → `Authorization: Bearer <your_agent_id>`
- MCP → the same Bearer token; the tool reads `ctx.caller_id`

From that identity the service derives your **role → permissions**, and it checks your
**membership** of the channel. A non-member receives `UNAUTHORIZED` and **never any data**.
This is what makes identity un-spoofable and keeps the CEO (or anyone) isolated to the
channels it legitimately belongs to.

Permissions:

| Permission | Who has it | Lets you |
|---|---|---|
| `chat:read` | everyone | read channels you're a member of |
| `chat:write` | agents (employee/COO/CEO/…) | post to channels you're a member of |
| `chat:manage` | agents | create channels, add members |
| `chat:system` | **only** a `coordinator`/`director` identity | read the **cross-channel firehose** (activation) |

> `chat:system` is deliberately **not** granted to any agent — not even the CEO — so no
> agent can read across channels it isn't in.

---

## Running it

```bash
# dev, zero infra (SQLite, no cache, no bus)
CHAT_DB_PATH=./data/chat.db python -m uvicorn services.internal_messaging.app.main:app --port 8085

# full production stack — Postgres + Redis + Kafka, all wired
docker compose up internal-messaging
```

Then seed at least one channel (an empty store rejects everything with `NOT_FOUND`):

```bash
CHAT_DB_PATH=./data/chat.db python -m services.internal_messaging.bootstrap
# -> creates the HT-2026-001 incident room (COO owner; EMP-QA-17 + CEO members)
```

Health check: `GET /health` → `{"status":"ok"}`.

### Backends (KB §2.3) — pluggable, chosen by env

Every backend has a **zero-infra default** (SQLite, no cache, no bus) so tests and
local dev need nothing running. The Docker deployment turns on the full stack:

| Concern | Env | Default (local) | Production (compose) |
|---|---|---|---|
| **Durable state** | `CHAT_STORE` | `sqlite` (`CHAT_DB_PATH`) | `postgres` (`CHAT_DB_URL`) |
| **Active state** | `CHAT_CACHE` | `none` | `redis` (`CHAT_REDIS_URL`) |
| **Events** | `CHAT_BUS` | `none` | `kafka` (`CHAT_KAFKA_BROKERS`, `CHAT_KAFKA_TOPIC`) |

Other: `CHAT_PORT` (default `8080`), `NTP_URL` (unset → local wall clock).

- **PostgreSQL** holds channels/memberships/messages; the append-only `messages`
  table is the durable, ordered event log (`seq` from a shared DB sequence).
- **Redis** holds active state: the channel-roster read-through cache and per-agent
  unread counters (derived; losing it is harmless).
- **Kafka** carries `chat.message_posted` — one topic, keyed by channel (per-channel
  ordering), payload includes `recipients` so a per-agent consumer filters its inbox
  and the Director gets the whole replayable log.

---

## What YOU must provide to integrate

1. **A registered identity + role.** Your `agent_id` must map to a role so you get
   permissions. The roster lives in `services/internal_messaging/integration/identity.py`
   (`default_registry()`); add your id there, or have your deployment inject it. Known
   ids today: `CEO-1` (ceo), `COO-1` (coo), `EMP-QA-17` + the employee personas
   (employee), `COORD-1` (coordinator). Unknown ids fall back to a plain `employee`.
2. **Channel membership.** You can only use channels you belong to. Either create one
   (`chat:manage`) or ask the owner to add you (`POST …/members`). The **Director** instead
   authenticates as a `coordinator` identity and reads the firehose — it needs no membership.
3. **(Optional) A shared clock** — set `NTP_URL` if you want `sent_at` to come from the
   world time service instead of local wall-clock.
4. **(Optional) A bus consumer** — if you'd rather be *pushed* events than poll, run with
   `CHAT_BUS=redis` and subscribe (see "Events" below). Polling works with no bus.

You do **not** need to change any of this service's code to integrate — you bring a client
and an identity; the service stays the same.

---

## How to use — REST door (any language)

Identity: `Authorization: Bearer <agent_id>`. All bodies/responses are JSON.

| Method & path | Perm | Body | Returns (`data`) |
|---|---|---|---|
| `POST /api/channels` | `chat:manage` | `{type, members[], name?, correlation_id?}` | `ChannelReceipt` |
| `GET /api/channels` | `chat:read` | — | `ChannelList` (yours only) |
| `POST /api/channels/{id}/members` | owner | `{agent_id, role?}` | `MembershipAck` |
| `POST /api/channels/{id}/messages` | `chat:write` + member | `{body, to?, source?}` | `MessageReceipt` |
| `GET /api/channels/{id}/messages?since=<seq>` | `chat:read` + member | — | `ChannelHistory` |
| `GET /api/messages?since=<seq>` | `chat:system` | — | cross-channel firehose |
| `GET /api/unread` | `chat:read` | — | `{channel: count}` (active state) |

`type` ∈ `direct` (exactly 2 members) · `group` · `incident` (carries `correlation_id`).
`since` is the monotonic **`seq`** cursor (an integer), not a timestamp — pass back the
`next_cursor` you got last time to fetch only newer messages.

Example (send + read):

```bash
curl -X POST http://localhost:8085/api/channels/$CID/messages \
  -H "Authorization: Bearer EMP-QA-17" -H "Content-Type: application/json" \
  -d '{"body":"LAB-781 POSITIVE on Line 4 @COO-1"}'

curl "http://localhost:8085/api/channels/$CID/messages?since=0" \
  -H "Authorization: Bearer COO-1"
```

Errors map to HTTP status: `VALIDATION`→400, `NOT_FOUND`→404, `UNAUTHORIZED`→403.

---

## How to use — MCP door (`mcp_core` agents: CEO, COO)

Same identity model, over Streamable-HTTP:

- `GET /mcp/chat/tools` — list the tool specs.
- `POST /mcp/chat/call` with `{ "tool": "chat.send_message", "args": {…} }` and
  `Authorization: Bearer <agent_id>` — returns the raw `ToolResult` envelope
  (`ok`, `value`, `error`, `meta`).

Tools: `chat.send_message`, `chat.read_channel`, `chat.list_channels`,
`chat.create_channel`, `chat.add_member`.

Your `mcp_core` client points at this endpoint with **no tool-code change**:

```python
from packages.mcp_core.http_client import HttpMCPClient
client = HttpMCPClient(http, agent_id="COO-1", base_url="http://internal-messaging:8085")
result = await client.call_tool("chat.send_message", {"channel": cid, "body": "…"}, ctx)
```

Over the wire `result.value` arrives as a dict inside the envelope; revalidate with the
schema (`MessageReceipt`) if you want typed access.

---

## Integration recipes (per team)

| You are… | Use | Steps |
|---|---|---|
| **CEO (Team 1)** | MCP | Point `HttpMCPClient` at `/mcp/chat`; register `CEO-1` (ceo); be a member only of its own channels (isolation is automatic). |
| **COO (Team 2)** | MCP | Same; your existing `chat.send_message` already matches — just set the base URL and be a channel member. |
| **Employee (Team 2)** | REST | Use the `SendChatMessage`/`ReadChannel` adapter (identity bound as Bearer). |
| **Any other language / system (Team 3)** | REST | Call `/api/*` with a Bearer id; `{success,data,error}`. |
| **Director / activation (Team 4)** | firehose | Authenticate as a `coordinator` id and poll `GET /api/messages?since=<seq>` — **or** subscribe to the bus (below). |

---

## Events & activation (for the Director)

The service **emits one event per message**; it does **not** decide who reacts. Two ways
to consume:

1. **Poll** `GET /api/messages?since=<seq>` (or per-channel `?since=`). Works with no infra.
2. **Subscribe to Kafka** (`CHAT_BUS=kafka`, the production default): each message is
   produced to the `chat.message_posted` topic, **keyed by channel** so a channel's events
   stay ordered on one partition. The payload carries `recipients`, so a per-agent consumer
   filters to its own inbox and the Director consumes the whole ordered, replayable log.
   (A Redis Streams transport — `CHAT_BUS=redis`, per-recipient `chat.inbox.<agent_id>`
   subjects — is also available for lighter setups.) Event fields: `channel`, `message_id`,
   `seq`, `mentions`, `trust_label`, `correlation_id`, `recipients`. **The body is not in the
   event** — follow `message_id` back via a read, so trust handling stays in one place.

---

## Guarantees & boundaries

**Guarantees**
- Identity can't be spoofed (taken from the connection, not the payload).
- CEO/agent isolation: you see only your channels; no agent gets the firehose.
- Message body is stored **verbatim** and returned verbatim, tagged with a `trust_label`
  (`internal` | `external` | `untrusted`). Chat labels; **it never sanitizes** — your input
  rails decide how much to trust it.
- The `messages` table is append-only and ordered by `seq`, so it *is* the replay log;
  deterministic under a fixed seed (build with `FixedClock` + `SeededIdFactory`).

**Not this service's job (owned elsewhere)**
- Announcements/broadcasts → Staff Portal · Audit log → Audit system · Email → BitriX Mail ·
  Public posts → Social Network · **deciding who wakes on an event → the Director**.

---

## Contracts

Payload models are in `packages/schemas/tool_results.py`:
`MessageReceipt`, `ChatMessage`, `ChannelHistory`, `ChannelSummary`, `ChannelList`,
`ChannelReceipt`, `MembershipAck`. The MCP contract primitives (`ToolContext`, `ToolSpec`,
`ToolResult`, `ErrorInfo`) are in `packages/mcp_core`. Full design rationale:
[`docs/internal_chat_v2_design.md`](../../docs/internal_chat_v2_design.md).

# Internal Messaging System (Internal Chat) — Service Design

> **⚠️ Implementation update — superseded in part (full stack landed).** This is the
> original clean-room design. Since it was written, the **production stack was built**
> (KB §2.3): the service now runs on **PostgreSQL** (durable state), **Redis** (active
> state — channel-roster cache + per-agent unread counters), and **Kafka** (events —
> `chat.message_posted`, one topic keyed by channel), all **pluggable** behind the
> zero-infra SQLite / no-cache / no-bus defaults described here. Consequently the
> "own SQLite" (§6), "not Kafka" (§8 D1, §12, §14) notes below reflect the **initial
> MVP choice, not the current implementation**. For the live backends, env matrix, and
> integration recipes see [`services/internal_messaging/INTEGRATION.md`](../services/internal_messaging/INTEGRATION.md).

> **Clean-room design.** Grounded **only** on three inputs, by request:
> 1. the **COO agent** contract on the `COO-Agent` branch (`packages/mcp_core`, `packages/schemas`,
>    `services/coo_agent/app/tools/mcp_clients.py`, `docs/mcp_contracts.md`);
> 2. the **non-chat docs** in this repo (`HappyTuna_BitriX_Use_Case_Knowledge_Base_v2.md`,
>    `AI_CEO_Crisis_Research.md`, `agent roles.md`, `company profile.md`, `tools.md`);
> 3. the **other repo's social network** (`../customer-influencer-agents/social_network`) as the proven
>    "business-system surface" pattern.
>
> It deliberately **does not** depend on, reference, or reuse any prior internal-chat code, the current
> coordinator implementation, or any `internal_chat_*` doc. Those are treated as if they do not exist.

---

## 1. What this system is (and is not)

The **Internal Messaging System** ("Internal Chat") is a **BitriX business system** — one of the
channels the KB says agents must communicate *through* (Real-World Interaction Principle; §1.8; §8).
In `agent roles.md` it is a listed tool of the **CEO, COO, and Employee**.

- It is a **surface**, not an agent: **no LLM, no reasoning**. It stores channels + messages, enforces
  who may read/write, labels untrusted content, and emits an event per change.
- It is **independently deployable** and reachable **over the wire** (KB Distributed Deployment: the CEO
  runs on its own machine and reaches company systems through APIs/MCP, never through shared memory).
- Its shape follows the **social network** in the other repo: a standalone service exposing **REST +
  an MCP endpoint on one process**, tools wrapping an in-process service layer (no self-HTTP),
  name-only identity, `{success, data?, error?}` envelope on REST.

**Not in scope (owned by other systems):**

| Concern | Owner (per COO contract / roles) |
|---|---|
| Announcements / broadcasts | **Staff Portal** — COO calls `portal.post_announcement` → `AnnouncementReceipt`, not chat |
| Immutable audit log | **Audit system** — `audit.append` → `AuditAck` |
| Email (1:1 formal mail) | **BitriX Mail** |
| Public posts | **Social Network** (other repo) |
| Global time | **NTP** time service (`tools.md`): "a global timing system determining the date and time for the world" |
| Deciding who wakes on an event | **Activation layer / Director** (KB §1.2, §10) — chat only *emits*; it does not activate |

So internal chat is intentionally small: **channels, membership, messages, trust labels, one event.**

---

## 2. Requirements it must satisfy

| # | Requirement | Source |
|---|---|---|
| R1 | Agents reach it **only through tools** (MCP) / API (REST); no peer memory access | KB §1.8, §8 |
| R2 | **Independently deployable**, reachable remotely (CEO on its own machine) | KB Distributed Deployment |
| R3 | Channels **direct / group / incident**; membership authorizes read+write | KB §4.1 |
| R4 | Honor the COO's **existing** tool: `chat.send_message {channel, body, to?}` → `ToolResult[MessageReceipt]`, identity from `ctx.caller_id` | COO `mcp_clients.py`, `tool_results.py` |
| R5 | Provide a **read** capability the COO contract is missing (define `ChannelHistory`) | gap in `schemas` |
| R6 | Every message body stored **verbatim as data**, tagged with a **trust label** | KB §4.3, §4.4 |
| R7 | **Role-based authorization** on every call: identity → permission → state → audit | KB §4.1; `mcp_core` `ToolContext`/`required_permission` |
| R8 | **CEO isolation** — sees only channels it belongs to; no privileged events | KB No-Privileged-CEO-Access, §2.3 |
| R9 | **Event per change** for activation + replay; `correlation_id` ties to incident | KB §1.2, §2.4, §10 |
| R10 | **Reproducibility** — time from NTP, deterministic ids | KB §6.6; `tools.md` |
| R11 | **Cross-language** reachable (TS social-net agents, Python agents) | KB §8; social-net repo |
| R12 | Return the standard **`ToolResult`** envelope with `ResultMeta` for audit/replay | `mcp_core` `result.py` |

---

## 3. The contract it must speak (from `mcp_core`)

Every tool is an `mcp_core.BaseTool`: it implements `spec: ToolSpec` + `async _run(args, ctx)`, and the
base wraps timing, `ResultMeta`, and uniform error capture so it **always returns a `ToolResult`** and
**never raises across the boundary**. This is fixed by the COO branch and we conform to it exactly.

```python
# mcp_core primitives we build against (verbatim from COO-Agent):
ToolContext(caller_id, caller_role, request_id, trace_id, idempotency_key, deadline, metadata)  # identity
ToolSpec(name, description, input_schema, side_effect: READ|WRITE, required_permission, version)  # declaration
ToolResult[T](ok, tool, value: T|None, error: ErrorInfo|None, meta: ResultMeta)                  # envelope
ErrorInfo(code: ErrorCode, message, retryable, details)   # code ∈ VALIDATION|NOT_FOUND|UNAUTHORIZED|
                                                          #        EXECUTION|TIMEOUT|UNAVAILABLE|...|INTERNAL
MCPError subclasses: ToolValidationError, ToolAuthorizationError, ToolExecutionError, ToolNotFoundError…
MCPClient / LocalMCPClient / ToolRegistry   # transport abstraction (local now, remote later, no caller change)
```

**Two rules the contract encodes, which shape the whole design:**
- *Communicate through systems only* — an agent reaches chat solely via an `MCPClient`/tool.
- *Authority is enforced* — identity + role come from `ToolContext`; the tool declares
  `required_permission` and `side_effect`; a guard checks them before executing.

Schemas conventions we reuse from `packages/schemas`: `SchemaModel` (base), `new_id(prefix)` (ids like
`msg_…`), `utcnow`, `ActorRef`.

---

## 4. Public tool surface (`chat.*`)

Namespaced `chat.*`, matching the COO's `chat.send_message`. The **send** tool's I/O is fixed by the COO
contract; the rest are additive and follow the same shape.

| Tool | side_effect | required_permission | input | value on success |
|---|---|---|---|---|
| `chat.send_message` | WRITE | `chat:write` | `{channel, body, to?}` | `MessageReceipt` |
| `chat.read_channel` | READ | `chat:read` | `{channel, since?}` | `ChannelHistory` *(new)* |
| `chat.list_channels` | READ | `chat:read` | `{}` | `ChannelList` *(new)* |
| `chat.create_channel` | WRITE | `chat:manage` | `{type, members[], name?, correlation_id?}` | `ChannelReceipt` *(new)* |
| `chat.add_member` | WRITE | `chat:manage` | `{channel, agent_id, role?}` | `MembershipAck` *(new)* |

### 4.1 `chat.send_message` — exact match to the COO's tool

```python
ToolSpec(
    name="chat.send_message",
    description="Post a message to an internal-chat channel you belong to.",
    input_schema={"type": "object", "required": ["channel", "body"],
                  "properties": {"channel": {"type": "string"},
                                 "body": {"type": "string"},
                                 "to": {"type": "array", "items": {"type": "string"}}}},
    side_effect=SideEffect.WRITE,
    required_permission="chat:write",
)
# _run: identity from ctx.caller_id (NEVER an arg). Enforce membership. Persist body verbatim.
#       Returns MessageReceipt(message_id, channel, delivered_to, sent_at).
```

`MessageReceipt` already exists in `packages/schemas/tool_results.py` — we return **exactly** it:

```python
class MessageReceipt(SchemaModel):
    message_id: str
    channel: str
    delivered_to: list[str]     # AUTHORITATIVE = current channel members (see §4.2)
    sent_at: datetime           # from NTP
```

### 4.2 Reconciling the COO's `to` argument with a channel model

The COO's mock sets `delivered_to = args["to"]`. In a real channel system the authoritative recipient
set is **the channel's membership**, not a caller-supplied list. Resolution (backward-compatible):

- `to` is **optional and advisory**. If the target channel is a `direct` channel or is being opened
  implicitly, `to` seeds/ensures those members; otherwise it is ignored.
- `MessageReceipt.delivered_to` in the response is **always the actual channel members** at send time.

This keeps the COO's existing calls valid while making delivery truthful and membership-driven (R3/R8).

### 4.3 The missing read type (`ChannelHistory`) — add to `packages/schemas`

The COO contract has **no** chat read tool and **no** history payload. We define it (R5), matching the
`tool_results.py` style, and add the alias next to `ChatToolResult`:

```python
class ChatMessage(SchemaModel):
    message_id: str
    seq: int                    # monotonic order cursor (see §6)
    sender: str
    body: str
    trust_label: str            # internal | external | untrusted
    mentions: list[str]
    sent_at: datetime

class ChannelHistory(SchemaModel):
    channel: str
    messages: list[ChatMessage]
    next_cursor: int            # pass back as `since` to fetch only newer messages

class ChannelSummary(SchemaModel):
    channel: str
    type: str                   # direct | group | incident
    name: str | None
    correlation_id: str | None
    member_count: int

class ChannelList(SchemaModel):
    channels: list[ChannelSummary]

class ChannelReceipt(SchemaModel):
    channel: str
    type: str
    created_at: datetime

class MembershipAck(SchemaModel):
    channel: str
    agent_id: str
    role: str

# aliases, alongside the existing ChatToolResult = ToolResult[MessageReceipt]
ChannelHistoryResult = ToolResult[ChannelHistory]
ChannelListResult    = ToolResult[ChannelList]
```

### 4.4 Failure mapping (uniform, per `mcp_core`)

| Situation | raise | becomes `ToolResult.error.code` |
|---|---|---|
| missing `channel`/`body` | `ToolValidationError` | `VALIDATION` |
| caller not a member | `ToolAuthorizationError` | `UNAUTHORIZED` |
| channel doesn't exist | `ToolNotFoundError` | `NOT_FOUND` |
| lacks `required_permission` | `ToolAuthorizationError` | `UNAUTHORIZED` |

`BaseTool` converts these to a failed `ToolResult` with `ResultMeta` — the tool never throws to the agent.

---

## 5. Channels & authorization (R3/R7/R8)

**Channel types** (announcements deliberately excluded — that's the staff portal):

| Type | Members | Use |
|---|---|---|
| `direct` | exactly 2 | 1:1 |
| `group` | ≥1 | multi-party room |
| `incident` | ≥1 | crisis room; carries `correlation_id` (incident id) |

**Roles:** `owner` (creator; may `add_member`) and `member`.

**Authorization pipeline** (KB §4.1), enforced once in the service layer for **both** MCP and REST:

```
identity (ctx.caller_id / Bearer)
  → required_permission present?        (chat:read | chat:write | chat:manage)
    → membership: is caller in channel? (read AND write require membership)
      → execute
        → emit event + it is now in the append-only log (audit)
```

A non-member receives `UNAUTHORIZED`, **never data**. This is the structural guarantee behind CEO
isolation (R8): the CEO is a member only of the channels it legitimately belongs to and can reach no
other — enforced by data, not by prompt.

---

## 6. Persistence — its own store; messages are the log (R6/R9)

Own database (SQLite at sim scale, like the social network and Email system). The `messages` table is
**append-only**, so it *is* the immutable event log the KB asks for (§2.4) — no separate outbox needed.

```sql
channels(   id PK, type, name, correlation_id, sim_time, seq )
memberships(channel_id, agent_id, role, sim_time, PRIMARY KEY(channel_id, agent_id))
messages(   id PK, seq, channel_id, sender_id, body, source, trust_label,
            mentions_json, correlation_id, sim_time )          -- INSERT-ONLY
-- indexes: messages(channel_id, seq), messages(seq)
```

- **`seq`** = a single monotonic integer (one source). It is the replay cursor **and** the `since`
  cursor. Order by `seq`, never wall-clock. Deterministic under a fixed seed.
- **`sim_time`** comes from **NTP** (the shared clock), never `datetime.now()` directly (R10).
- **`id`** via the shared `new_id("msg")` / `new_id("chan")` convention; a seeded variant makes ids
  deterministic for replay (R10; see §9).

---

## 7. Trust boundary (R6) — label, never sanitize

```
source            → trust_label
internal (default)  internal
external            external
anonymous/unknown   untrusted
```

- `body` is stored **exactly as received** and returned **exactly as stored**. Chat never interprets it,
  strips it, or treats any substring as an instruction (KB §4.3).
- `trust_label` travels with the message everywhere (store → `ChatMessage` → REST → event), so the
  *consuming agent's* input rails (KB §4.4) decide how much to trust it. Chat's job is to **label**.
- Note: the COO's `chat.send_message` has no `source` arg; internal agent traffic defaults to
  `internal`. `source` is accepted as an **optional** field (backward-compatible) so external-origin
  content relayed into a channel can be correctly labeled `external`/`untrusted`.

---

## 8. Events & activation (R9/R8)

Chat **emits one event per state change**; it does **not** decide who reacts. The activation layer /
Director (KB §1.2, §10) consumes events and wakes the right agent. Chat stays dumb and reusable.

```json
{
  "eventType": "chat.message_posted",
  "actorId": "EMP-QA-17",
  "simTime": "DAY_1_09:30",
  "correlationId": "HT-2026-001",
  "seq": 9001,
  "payload": {
    "channel": "chan_00123",
    "messageId": "msg_09001",
    "mentions": ["COO-1"],
    "trustLabel": "internal",
    "recipients": ["COO-1", "EMP-QA-17"]
  }
}
```

- **Body is not in the event** (content plane vs. event plane): consumers follow `messageId` back via
  `chat.read_channel`. Keeps trust handling in one place.
- **Role-scoped delivery (R8):** `recipients` = current channel members; the publisher targets
  per-recipient subjects (`chat.inbox.<agent_id>`) or tags the event for a bus ACL. An agent **cannot**
  receive an event for a channel it isn't in — CEO isolation by construction.
- **Transport is a seam, not a hard dependency:** the same data is available by **polling**
  `chat.read_channel {since}` / `GET …/messages?since=<seq>`, so chat is usable before any bus exists.
  (Bus choice — NATS/JetStream or Redis Streams per KB §2.3 — is the Director's; not a chat dependency.)
- Event shape follows `packages/schemas` conventions (`SchemaModel`, `new_id`, `utcnow`, `ActorRef`) and
  is added there as the cross-team contract.

---

## 9. Reproducibility (R10) — designed in

Two injected collaborators, matching the shared-tools reality (`tools.md`: NTP is a world service):

```python
class Clock(Protocol):    def now(self) -> datetime: ...     # NtpClock (shared) | WallClock (local dev)
class IdFactory(Protocol):
    def new(self, prefix: str) -> str: ...                   # SeededIdFactory (deterministic) | new_id
    def next_seq(self) -> int: ...                           # single monotonic source for `seq`
```

- The store **never** calls `datetime.now()`/`uuid4()` directly — it stamps rows from the injected
  `Clock` + `IdFactory` (wired via DI, overridden with deterministic fakes in tests).
- Result: same seed ⇒ identical channel/message ids, `seq` ordering, and `sim_time`. One test asserts it.
- Local dev defaults to `WallClock` + `new_id`; swap to `NtpClock` + `SeededIdFactory` with **no schema
  change** (only how columns are populated).

---

## 10. Service shape & deployment (R1/R2/R11)

One process, two faces, one service layer, one store — the social-network pattern:

```
services/internal_messaging/
  app/main.py          FastAPI factory: mounts MCP endpoint (/mcp/chat) + REST (/api/*) + /health
  app/config.py        env only: DB path, port, BUS_URL, NTP_URL, REGISTRY_URL, seed
  app/deps.py          DI: service, caller-identity, clock, id-factory, publisher
  transport/mcp/       BaseTool subclasses (chat.*) registered in a ToolRegistry/LocalMCPClient
  transport/rest/      thin routers mirroring the tools (cross-language + polling fallback)
  domain/service.py    ALL rules + authorization (single source of truth for MCP and REST)
  domain/store.py      SQLite; append-only messages
  domain/trust.py      source → label; mention parse
  integration/         events(publisher+recipients) · clock(Ntp|Wall) · ids · identity(registry)
  tests/               store · authz/isolation · trust-verbatim · mcp round-trip · events · reproducibility
  Dockerfile
```

- **MCP** (`/mcp/chat`, Streamable-HTTP) is the primary door for `mcp_core`-based agents (COO, CEO,
  employees). Register `chat.*` tools in a `LocalMCPClient` now; a **remote** transport later needs
  **no** change to the tools or the COO (the `MCPClient` abstraction guarantees this).
- **REST** (`/api/*`, OpenAPI, `{success,data,error}`) is the universal door for TS/social-net agents,
  the Director, and debugging/polling (R11).
- **Identity is name-only** (matches social-net + Email): MCP → `ctx.caller_id`; REST →
  `Authorization: Bearer <agent_id>`. A **registry** maps `agent_id → role → permissions`
  (`chat:read|write|manage`). Security depth is explicitly out of scope per the KB and the social net.
- **Deployment:** its own container in the world compose; the CEO on its own machine reaches it at
  `http://internal-messaging:PORT/mcp/chat`. Tables auto-create on first start.

---

## 11. How each party integrates

The service is reached **over the wire (MCP or REST)**, so it is **framework-neutral**: an agent's own
tool framework only decides which door it uses and what client adapter it brings — never the service.
The two frameworks in play:

- **`mcp_core` agents (COO, CEO):** use the **MCP** door (`/mcp/chat`) via an `MCPClient`; identity is
  `ctx.caller_id`; results are `ToolResult[T]`.
- **`agentkit` agents (Employee):** use the **REST** door via a thin `ToolBase` adapter; identity is the
  **bound** `agent_id` injected as `Authorization: Bearer <agent_id>` (never an LLM argument — this
  closes the identity-spoofing gap of passing `sender_id` as a parameter); writes set
  `is_idempotent=False` so they run exactly once.

> Consequence: you do **not** need to reconcile the two frameworks to make every agent work — each keeps
> its own and meets chat at the wire. Reconciliation only matters for a single shared *in-process* tool
> object, which this over-the-wire design avoids.

| Party | Door | Does |
|---|---|---|
| **COO** (ready) | MCP | Point its existing `chat.send_message` `MCPClient` at the real endpoint; register `COO-1` with `chat:write`+`chat:read`; be a channel member. No tool code change. |
| **CEO** | MCP | Same as COO via `mcp_core`; is a member only of its own channels (R8). |
| **Employee** | REST | Thin `agentkit.ToolBase` adapter → `POST /api/channels/{id}/messages` / `GET …?since=`; identity bound, not an LLM arg. |
| **TS / social-net agents** | REST | Same REST surface, any language. |
| **Activation layer / Director** | events | Consume `chat.message_posted` (or poll `since`); provide NTP, registry, seed. |

---

## 12. Prerequisites & open decisions

**Hard prerequisites (external to chat):**
1. `packages/mcp_core` + `packages/schemas` (incl. `MessageReceipt`) available on the working branch —
   today they live on the `COO-Agent` branch.
2. Team agreement that `mcp_core` is **the** shared tool contract.

**Cross-team contracts to lock first (the real "from-0" artifacts):**
- `ChannelHistory` / `ChatMessage` / channel payloads (§4.3) — added to `packages/schemas`.
- `chat.message_posted` event shape + topic namespace + recipient/ACL convention (§8).
- Identity registry format + permission names `chat:read|write|manage` (§10).
- NTP clock protocol + seed/id convention (§9).

| # | Open decision | Default |
|---|---|---|
| D1 | Event bus product | NATS/JetStream or Redis Streams (Director's call); not Kafka |
| D2 | `to` semantics on `send_message` | advisory; `delivered_to` = channel members (§4.2) |
| D3 | Keep REST face? | Yes — needed for TS agents / Director / polling |

---

## 13. Build phases

| Phase | Deliverable | Satisfies |
|---|---|---|
| P0 | `store.py` + `service.py` + SQLite; injected `Clock`/`IdFactory` | R3, R10 core |
| P1 | Membership authz + trust labels + `chat.*` **service** methods | R3, R6, R7, R8 |
| P2 | **MCP** tools (`chat.*`) against `mcp_core`; add `ChannelHistory` etc. to `schemas` | R4, R5, R12 |
| P3 | **REST** face (mirror) | R11 |
| P4 | Event publisher + role-scoped recipients; `chat.message_posted` | R9, R8 |
| P5 | Dockerfile + compose; remote-reachable; NTP + seeded ids | R2, R10 |

P0–P2 proceed even before a bus exists (polling via `since`). The COO can call chat as soon as P2 lands.

---

## 14. Explicit non-goals

No LLM/reasoning · no announcements (staff portal) · no audit log (audit system) · no email · no content
sanitization (label only) · no Kafka/outbox (append-only log is durable) · no shared process with any
agent · no cross-agent memory access, ever.
```

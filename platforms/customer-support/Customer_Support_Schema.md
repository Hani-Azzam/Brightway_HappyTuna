# Customer support schema — Team 3

## Overview

Two structures, designed to be built once and extended without breaking:

1. **Ticket** — the current state of a customer support case.
2. **Ticket activity log entry** — an append-only log entry. Every ticket change writes one entry here. A ticket's "history" is just `ticket_activity_log where entity_id = ticket_id`, not a field stored on the ticket itself.

This activity log table is intentionally generic (`entity_type` + `entity_id`) so Social Network posts, agent decisions, or anything else can log into the same table later without a schema change. (Note: this is unrelated to the crisis "world events" your Event Generator will fire — that's a separate, not-yet-designed piece of work.)

---

## 1. Ticket schema

```json
{
  "ticket_id": "TCK-00231",
  "customer_id": "CUST-1190",
  "created_at": "2026-06-23T10:14:00Z",
  "updated_at": "2026-06-23T10:14:00Z",
  "status": "open",
  "priority": "high",
  "issue_type": "safety_concern",
  "subject": "Metal fragment in canned tuna",
  "description": "Found a sharp piece of metal in batch #4471, this is dangerous.",
  "linked_product_batch": "4471",
  "sentiment": "angry",
  "sentiment_method": "keyword_v1",
  "assignee": null,
  "reply_message": null,
  "schema_version": 1
}
```

### Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `ticket_id` | string | yes | unique, format `TCK-#####` |
| `customer_id` | string | yes | references the customer agent |
| `created_at` | timestamp (ISO 8601) | yes | set once, never changes |
| `updated_at` | timestamp (ISO 8601) | yes | bump on every state change |
| `status` | enum | yes | `open`, `in_progress`, `escalated`, `resolved`, `closed` |
| `priority` | enum | yes | `low`, `medium`, `high`, `critical` |
| `issue_type` | enum | yes | `quality`, `delivery`, `billing`, `general`, `safety_concern` |
| `subject` | string | yes | short, agent-generated |
| `description` | string | yes | full complaint text, agent-generated |
| `linked_product_batch` | string \| null | no | batch/lot number if relevant; null otherwise |
| `sentiment` | enum \| null | no | `angry`, `frustrated`, `neutral`, `positive`; null if not yet scored |
| `sentiment_method` | string \| null | no | which scorer produced it, e.g. `keyword_v1` — lets you swap scorers later and know which tickets used which version |
| `assignee` | string \| null | no | id of the COO/employee agent who owns this ticket; null until assigned |
| `reply_message` | string \| null | no | most recent reply sent to the customer; null until a reply exists |
| `schema_version` | integer | yes | starts at `1`; bump if you ever change the shape of this object |

### Why `assignee` and `reply_message` live on the ticket too, not just in the log

The activity log already records every assignment and every reply as its own entry (`assigned`, `replied`) — that's the full history. `assignee` and `reply_message` on the ticket itself are just a convenience snapshot of the *current* assignee and *most recent* reply, so a simple `GET /tickets/{id}` can answer "who owns this right now" and "what did we last tell the customer" without a second call to fetch the activity log. If you need the full reply thread, read the log.

### Why `sentiment_method` and `schema_version` are in here

Both exist purely to make future changes safe:

- If you replace the keyword scorer with a real classifier later, old tickets keep their `keyword_v1` tag instead of silently looking like they came from the new model. You can re-score old tickets in bulk later if you want, without guessing which ones need it.
- If the ticket shape changes (new required field, renamed field), `schema_version` lets your code branch on old vs. new tickets instead of assuming every record matches today's shape.

### Current scorer (`keyword_v1`) — what it can and can't do

`score_sentiment()` in `storage.py` checks angry → frustrated → positive keyword/phrase sets in order, with a basic negation check (skips a match if a negation word like `not`/`don't`/`isn't` appears in the two tokens before it). It correctly produces all four enum values now, including `frustrated`, and handles common contractions.

It's still keyword-based, so it will miss: sarcasm, multi-sentence tone shifts, and any phrasing not in the keyword lists. That's expected — this is intentionally the cheap, deterministic v1.

**Planned upgrade:** once the Customer agent is wired to an LLM (week 3), have that same LLM call also return a sentiment label as structured output, with the keyword scorer kept as a fallback if that call fails. Tag those results `sentiment_method: "llm_v1"` (or similar) so old and new scoring methods stay distinguishable in the data. Don't build this before the agent LLM wiring exists — it would mean building the sentiment logic twice.

### `issue_type = safety_concern` — when to use it

Use this instead of `quality` whenever the complaint involves:
- a foreign object in the product
- suspected contamination (smell, discoloration, mold)
- reported illness after consumption
- a swollen or bulging can
- mislabeled allergen information

This is the field your Event Generator and routing logic should treat as a deterministic trigger — a `safety_concern` ticket is what justifies activating the COO / quality lab, independent of how angry the customer sounds.

---

## 2. Ticket activity log schema (shared log — covers ticket history and more)

```json
{
  "log_id": "LOG-000991",
  "entity_type": "ticket",
  "entity_id": "TCK-00231",
  "activity_type": "status_changed",
  "timestamp": "2026-06-23T11:02:00Z",
  "actor": "COO-1",
  "details": {
    "from": "open",
    "to": "in_progress"
  },
  "schema_version": 1
}
```

### Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `log_id` | string | yes | unique, format `LOG-######` |
| `entity_type` | string | yes | `ticket` for now; `post`, `agent_decision`, etc. later — no schema change needed |
| `entity_id` | string | yes | the id of the thing this activity happened to |
| `activity_type` | string | yes | free-form but should come from a known set per entity_type (see below) |
| `timestamp` | timestamp (ISO 8601) | yes | when it happened |
| `actor` | string | yes | who/what caused it — agent id, system name, or `"system"` |
| `details` | object | no | activity-specific payload, shape varies by `activity_type` |
| `schema_version` | integer | yes | same purpose as on the ticket |

### Known `activity_type` values for `entity_type = "ticket"`

| activity_type | When it fires | Example `details` |
|---|---|---|
| `created` | ticket filed | `{}` |
| `status_changed` | status field updated | `{ "from": "open", "to": "escalated" }` |
| `priority_changed` | priority updated | `{ "from": "medium", "to": "critical" }` |
| `assigned` | a COO/employee agent takes ownership | `{ "assignee": "COO-1" }` |
| `replied` | a response sent to the customer | `{ "message": "..." }` |
| `sentiment_scored` | sentiment field set/updated | `{ "sentiment": "angry", "method": "keyword_v1" }` |

This list isn't closed — add new `activity_type` values as you need them. Nothing about the schema requires a fixed list, this table is just documentation so the team doesn't invent inconsistent names independently (e.g. one person writes `status_change`, another writes `statusUpdated`).

### Getting a ticket's full history

```
ticket_activity_log.filter(e => e.entity_type === "ticket" && e.entity_id === "TCK-00231")
                   .sort(by timestamp)
```

That's the entire "history" feature. No separate field on the ticket, no separate service — just a filtered, sorted read of the shared ticket activity log.

---

## 3. How this stays easy to update later

- **New ticket field needed?** Add it as optional/nullable first. Old tickets without it simply have it as `null` or absent; nothing breaks. Bump `schema_version` only if the change is structural (e.g. renaming or removing a field).
- **New activity type needed?** Just start using it and add a row to the table above. No migration needed since `activity_type` is a string, not a hard enum at the storage level.
- **Want richer sentiment later?** Swap the scorer, write the new value with `sentiment_method: "classifier_v2"`, leave old tickets alone. Both versions can coexist.
- **Need cross-entity activity logs (Social Network posts, agent decisions)?** Reuse the same ticket activity log table (consider renaming it to a more general `activity_log` once it covers more than tickets) with a different `entity_type`. No new system to build.
- **Need a separate activity-log microservice eventually** (e.g. for Team 4's evaluation/replay needs in week 5)? The shape already matches what a dedicated log store would look like — migrating later is a deployment change, not a schema rewrite.

---

## 4. Open items for week 1 sync

- Confirm with Team 2 what their internal escalation/audit activity looks like, so `actor` values (e.g. `COO-1`, `EMP-4`) and any shared `activity_type`s line up rather than each team inventing its own naming.
- Confirm with Team 4 whether their (crisis) event engine expects a specific envelope format — if so, this ticket activity log should be able to also serve as (or feed into) that format without duplication.
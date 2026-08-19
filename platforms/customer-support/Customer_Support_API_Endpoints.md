# Customer Support API — endpoint reference

Team 3 — Customer Support system. Signatures only; this is the contract to build against, not the implementation.

Companion docs: `Customer_Support_Schema.md` (ticket + activity log schema), `PROJECT_README.md` (project-wide context).

---

## Design decisions locked in

1. **One update rule.** Everything that changes a ticket goes through `PATCH /tickets/{ticket_id}` — including assignment and replies, not just status/priority. There is no separate endpoint for logging actions.
2. **Auto-logging.** The server diffs old vs. new values on every `PATCH` and writes the matching activity-log entry automatically. Callers never write to the log directly.
3. **No pagination.** List endpoints return the full matching result set. Add `page`/`limit` later only if a real scenario produces enough tickets to need it — not before.

---

## Tickets

### `POST /tickets`

Creates a new ticket.

**Body:**
| Field | Required | Notes |
|---|---|---|
| `customer_id` | yes | |
| `issue_type` | yes | `quality`, `delivery`, `billing`, `general`, `safety_concern` |
| `subject` | yes | |
| `description` | yes | |
| `linked_product_batch` | no | null if not relevant |
| `priority` | no | defaults to `medium` |

**Response:** full ticket object. `status` is auto-set to `open`.

**Auto-logs:** one activity-log entry, `activity_type: "created"`.

---

### `GET /tickets/{ticket_id}`

Returns one ticket by id.

**Response:** full ticket object, or 404 if not found.

---

### `GET /tickets`

Lists/filters tickets. All filters are optional and combinable.

**Query params:**
| Param | Notes |
|---|---|
| `customer_id` | tickets for one customer |
| `status` | `open`, `in_progress`, `escalated`, `resolved`, `closed` |
| `issue_type` | e.g. filter to `safety_concern` only |
| `linked_product_batch` | e.g. every ticket referencing batch `4471` |

**Response:** array of full ticket objects. No pagination — returns everything matching.

**Example:** `GET /tickets?status=open&issue_type=safety_concern`

---

### `PATCH /tickets/{ticket_id}`

Updates one or more fields on a ticket. This is the only write path for changes after creation.

**Body (any subset of):**
| Field | Notes |
|---|---|
| `status` | triggers `status_changed` log entry |
| `priority` | triggers `priority_changed` log entry |
| `sentiment` | triggers `sentiment_scored` log entry |
| `assignee` | triggers `assigned` log entry |
| `reply_message` | triggers `replied` log entry (message text goes in the log entry's `details`) |

**Response:** the updated ticket object.

**Auto-logs:** one activity-log entry per changed field, written automatically by the server. Callers do not log anything themselves.

**Note:** `assignee` and `reply_message` aren't in the original ticket schema doc yet — add them there before/while building this endpoint so the schema and API stay in sync.

---

## Ticket activity log

### `GET /tickets/{ticket_id}/activity`

Returns the full activity log for one ticket, sorted by timestamp ascending.

**Response:** array of activity-log entries (see `Customer_Support_Schema.md` for the entry shape).

**Read-only.** There is no corresponding write endpoint — all log entries are created automatically as a side effect of `PATCH`.

---

## Summary table

| Method | Path | Purpose |
|---|---|---|
| POST | `/tickets` | create a ticket |
| GET | `/tickets/{ticket_id}` | get one ticket |
| GET | `/tickets` | list/filter tickets |
| PATCH | `/tickets/{ticket_id}` | update any field; auto-logs the change |
| GET | `/tickets/{ticket_id}/activity` | read a ticket's full history |

6 endpoints total. Nothing else needed for the MVP.

---

## Open follow-up

- Update `Customer_Support_Schema.md` to add `assignee` and `reply_message` as ticket fields, so the schema matches what `PATCH` actually accepts.

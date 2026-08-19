# Customer Support System

FastAPI backend + React monitoring dashboard for the HappyTuna crisis-simulation project (Team 3).

---

## Running with Docker (recommended)

This service is part of the project-wide `docker-compose.yml` at the repo root. From the repo root:

```bash
docker compose up --build
```

This builds and starts every team's service at once, including this one. See the root `PROJECT_README.md` for the full picture.

To rebuild just this service after changing code, without rebuilding everything else:

```bash
docker compose up --build customer-support-api
docker compose up --build customer-support-dashboard
```

### Why there are two Dockerfiles

This service is actually two separate containers:

| | Location | What it does |
|---|---|---|
| **API** | `Customer_Support_System/Dockerfile` | Python container running the FastAPI backend (`main.py`) — serves the ticket endpoints |
| **Dashboard** | `Customer_Support_System/cs-monitor/Dockerfile` | Node container that builds the React dashboard into static files, then serves them |

They're separate because they need completely different environments (Python vs. Node) — one Dockerfile can't sensibly do both. The dashboard's container runs `npm run build` once, then serves the compiled static site; it isn't running a dev server inside Docker.

### Ports

| Service | Port | Why |
|---|---|---|
| `customer-support-api` | **8003** (external) → 8001 (inside container) | 8001 was already taken by `customer-agent` in the shared `docker-compose.yml`, so this service uses 8003 externally to avoid the collision |
| `customer-support-dashboard` | **5173** | Vite's default dev port, kept the same in production for consistency |

The dashboard's `BASE_URL` (in `cs-monitor/src/Dashboard.jsx`) must always point at **8003** — if you ever change the API's port mapping in `docker-compose.yml`, update `BASE_URL` to match, then rebuild the dashboard container.

---

## Running locally without Docker

Useful for quick iteration without rebuilding containers.

**Terminal 1 — API:**
```bash
cd Customer_Support_System
pip install -r requirements.txt
uvicorn main:app --port 8003 --reload
```

**Terminal 2 — Dashboard:**
```bash
cd Customer_Support_System/cs-monitor
npm install
npm run dev
```

Open `http://localhost:5173` for the dashboard, `http://localhost:8003/docs` for Swagger.

Keep using **8003** locally too (not 8001) — that way the code doesn't need different config for local vs. Docker.

### CORS

The API allows requests from `http://localhost:5173` via `CORSMiddleware` in `main.py`. This only matters for **browser-based calls** (the dashboard) — other teams' agents calling this API from backend code aren't affected by CORS at all.

---

## MCP server (for agents)

Alongside the REST API, this service also exposes an **MCP server** (`mcp_server.py`) — the same underlying operations, but as MCP tools instead of HTTP endpoints. This is what agents (Customer, Influencer, COO, etc.) should use to interact with Customer Support, rather than making raw HTTP calls.

Both the REST API and the MCP server call the same `storage.py` functions and share the same SQLite database — a ticket created via an MCP tool call shows up in the dashboard immediately, and vice versa. Verified safe for concurrent use from separate containers (tested with 5 simultaneous processes writing to the same database file with zero collisions or corruption).

### Available tools

| Tool | Mirrors | Purpose |
|---|---|---|
| `create_ticket` | `POST /tickets` | File a new ticket. Sentiment is auto-scored from the description. |
| `get_ticket` | `GET /tickets/{id}` | Fetch one ticket by id. |
| `list_tickets` | `GET /tickets` | List/filter tickets. Returns `{"count": N, "tickets": [...]}`. |
| `patch_ticket` | `PATCH /tickets/{id}` | Update any field; auto-logs the change. |
| `get_activity_log` | `GET /tickets/{id}/activity` | Full history for a ticket. Returns `{"count": N, "entries": [...]}`. |

### Connecting to it

The server runs on **streamable-http** transport (not stdio), since agents live in separate containers and need to reach it over the network, not as a local subprocess.

| Caller | URL |
|---|---|
| From your own machine (manual testing) | `http://localhost:8010/mcp` |
| From another container on the same Docker network (e.g. the Customer agent) | `http://customer-support-mcp:8010/mcp` |

Containers reach each other by **service name**, not `localhost` — `localhost` inside a container only refers to that container itself.

### Example: an agent calling a tool

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def file_ticket():
    async with streamablehttp_client("http://customer-support-mcp:8010/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("create_ticket", {
                "customer_id": "CUST-1190",
                "issue_type": "safety_concern",
                "subject": "Metal fragment in tuna",
                "description": "Found something sharp in my can, this is dangerous",
                "linked_product_batch": "4471",
            })
            print(result.content[0].text)
```

### Running it

Via Docker (recommended — see root `docker-compose.yml`):
```bash
docker compose up --build customer-support-mcp
```

Locally without Docker:
```bash
cd Customer_Support_System
pip install -r requirements.txt
python mcp_server.py
```

---

## Example requests

### 1. Create a ticket

```bash
curl -s -X POST http://localhost:8003/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "CUST-1190",
    "issue_type": "safety_concern",
    "subject": "Metal fragment in canned tuna",
    "description": "Found a sharp piece of metal in batch #4471.",
    "linked_product_batch": "4471",
    "priority": "high"
  }' | python -m json.tool
```

Example response:

```json
{
  "ticket_id": "TCK-00001",
  "customer_id": "CUST-1190",
  "created_at": "2026-06-27T10:00:00.000000+00:00",
  "updated_at": "2026-06-27T10:00:00.000000+00:00",
  "status": "open",
  "priority": "high",
  "issue_type": "safety_concern",
  "subject": "Metal fragment in canned tuna",
  "description": "Found a sharp piece of metal in batch #4471.",
  "linked_product_batch": "4471",
  "sentiment": "angry",
  "sentiment_method": "keyword_v1",
  "assignee": null,
  "reply_message": null,
  "schema_version": 1
}
```

---

### 2. Patch the ticket's status (and set the actor)

```bash
curl -s -X PATCH http://localhost:8003/tickets/TCK-00001 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress",
    "actor": "COO-1"
  }' | python -m json.tool
```

The server diffs old vs. new values automatically and writes a `status_changed`
activity-log entry. The caller never touches the log directly.

---

### 3. Fetch the activity log — confirm the auto-log entry appeared

```bash
curl -s http://localhost:8003/tickets/TCK-00001/activity | python -m json.tool
```

Example response (two entries: creation + status change):

```json
[
  {
    "log_id": "LOG-000001",
    "entity_type": "ticket",
    "entity_id": "TCK-00001",
    "activity_type": "created",
    "timestamp": "2026-06-27T10:00:00.000000+00:00",
    "actor": "system",
    "details": {},
    "schema_version": 1
  },
  {
    "log_id": "LOG-000002",
    "entity_type": "ticket",
    "entity_id": "TCK-00001",
    "activity_type": "status_changed",
    "timestamp": "2026-06-27T10:01:00.000000+00:00",
    "actor": "COO-1",
    "details": {
      "from": "open",
      "to": "in_progress"
    },
    "schema_version": 1
  }
]
```

---

### 4. Filter tickets by issue_type=safety_concern

```bash
curl -s "http://localhost:8003/tickets?issue_type=safety_concern" | python -m json.tool
```

Combine filters freely — all query params are optional:

```bash
# Safety tickets that are still open, for a specific batch
curl -s "http://localhost:8003/tickets?issue_type=safety_concern&status=open&linked_product_batch=4471"
```

---

## Auto-logging rules

`PATCH /tickets/{ticket_id}` diffs old vs. new for each field and writes one
log entry per changed field:

| Changed field   | `activity_type`   | `details` shape                                      |
|-----------------|-------------------|------------------------------------------------------|
| `status`        | `status_changed`  | `{"from": "open", "to": "in_progress"}`              |
| `priority`      | `priority_changed`| `{"from": "medium", "to": "critical"}`               |
| `sentiment`     | `sentiment_scored`| `{"sentiment": "angry", "method": "keyword_v1"}`     |
| `assignee`      | `assigned`        | `{"assignee": "COO-1"}`                              |
| `reply_message` | `replied`         | `{"message": "We are investigating your complaint."}`|

Pass `"actor"` in the PATCH body to attribute the change (defaults to
`"system"` when omitted). `sentiment_method` can be patched alongside
`sentiment`; it is included in the `sentiment_scored` log details but does
not generate its own log entry.

## Enum values

| Field         | Accepted values                                            |
|---------------|--------------------------------------------------------------|
| `status`      | `open`, `in_progress`, `escalated`, `resolved`, `closed`  |
| `priority`    | `low`, `medium`, `high`, `critical`                        |
| `issue_type`  | `quality`, `delivery`, `billing`, `general`, `safety_concern` |
| `sentiment`   | `angry`, `frustrated`, `neutral`, `positive`               |

Invalid values return `422 Unprocessable Entity` automatically.

## Sentiment scoring

Sentiment is auto-computed at ticket creation by `score_sentiment()` in
`storage.py` (`keyword_v1`): keyword/phrase matching for angry, frustrated,
and positive, with basic negation handling (skips a match if a negation
word appears within 2 tokens before it). See `samples.py` for test cases,
including the documented 2-token negation-window limit.

**Planned upgrade:** once the Customer agent is wired to an LLM, that same
call can also return a sentiment label (`llm_v1`), with the keyword scorer
kept as a fallback.

## Running the test suite

```bash
python samples.py
```

Runs 9 sample tickets through the sentiment scorer and prints pass/fail
against expected results, plus the activity log for the first ticket.
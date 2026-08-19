# BitriX / HappyTuna crisis-simulation project

This file is the shared context for the whole project. Attach it to every piece you build (schema, service, agent, diagram) so anyone picking up your work — teammates, other teams, or future you — can understand what it fits into without re-reading every doc from scratch.

---

## 1. What we're building

A multi-agent simulated world (**BitriX**) around a fictional company (**HappyTuna**, a canned-tuna food manufacturer) used to study how a **CEO AI agent** handles a real organizational crisis.

- **Research subject:** the CEO agent. Its decisions, communication, and crisis-management quality are what's actually being measured.
- **Everything else** — COO, employees, board, customers, influencers, journalists, regulators, and all the business systems — is the simulated environment the CEO operates inside. These roles are realistic, but they are not what's being scored.

The company profile: HappyTuna, ~500 employees, $250M revenue, top-3 tuna brand, high-trust family-brand reputation. That reputation is the thing a crisis (e.g. contamination) puts at risk.

---

## 2. The simulation loop (how one "round" works)

```
Event generator → Shared systems → Agents react → CEO decides → Systems update → Evaluation scores → (next event)
```

1. **Event generator** injects something (e.g. a contamination rumor, a regulator notice).
2. It lands in **shared systems** (News Portal, Social Network, CRM, Mail, etc.) — every agent only ever sees the world through these systems, never through another agent's private internals.
3. **Agents react** — customers complain, journalists publish, influencers amplify, employees report.
4. **CEO decides**, reading the same systems, and posts a public/internal response.
5. That response becomes **new posts and tickets**, which can trigger further reactions — this is what makes a crisis cascade rather than die out after one round.
6. **Evaluation** scores the CEO's handling of the round (detection, decision quality, communication, containment, recovery).
7. The loop feeds into the next event.

**Hard rule:** the CEO must never get hidden information (ground truth, other agents' private state, future events, the evaluation score). It only sees what a real CEO would see through real company channels.

---

## 3. The four teams (actual split)

| | Team 1 | Team 2 | Team 3 (us) | Team 4 |
|---|---|---|---|---|
| **Agents** | CEO, Board | Employee, COO | Customer, Influencer | Journalist, Regulator |
| **Core systems** | Email system | Internal Chat | Social Network, Customer Support | News Website |
| **Optional system** | Quality lab | Staff Portal | — | CRM |
| **Other** | Weather | Audit | Event Generator | NTP |

Notes:
- The split isn't based on "internal vs external" or any single clean principle — it's just how the four teams were divided. Don't over-infer structure from it.
- Team 3 is the only team with **no optional system** — Social Network, Customer Support, and the Event Generator are all required for the simulation to function.
- Team 3 **owns the Event Generator outright** — no other team controls when crisis events fire.

### How the teams connect

- **Team 1 ↔ Team 2:** internal governance and reporting (CEO/Board ↔ Employee/COO)
- **Team 2 ↔ Team 4:** leaks and audits (Employee/COO ↔ Journalist/Regulator)
- **Team 3 ↔ Team 4:** public reactions and news (Customer/Influencer ↔ Journalist/Regulator)
- **Team 1 ↔ Team 3:** public sentiment reaching leadership, statements going out (CEO/Board ↔ Customer/Influencer)

All communication happens **through systems**, never agent-to-agent directly. No service may read another service's private memory or prompt state.

---

## 4. Our team's scope (Team 3)

**Agents:** Customer, Influencer (each implemented as multiple personas, not one generic actor)
- Customers: loyal, vocal/complainer, price-sensitive, risk-sensitive
- Influencers: consumer-rights, sensational, brand-supporter

**Systems:** Social Network (posts, comments, reactions, trends), Customer Support (tickets)

**Owned:** Event Generator (fires crisis events into the world)

**What we're evaluated on indirectly:** our agents and systems aren't research subjects themselves, but they need to be realistic, reproducible, and free of information leakage — that's what makes the CEO's evaluation meaningful.

---

## 5. Event-type → activation routing (reference)

| Event type | Activates | Trigger type |
|---|---|---|
| Quality alert | COO | Deterministic |
| Lab/test result | COO + relevant employees | Deterministic |
| Information leak | Journalist | Deterministic |
| Published news article | Customers + influencers + board | Deterministic |
| High public-health risk | Regulator | Deterministic |
| Regulatory notice | CEO | Deterministic |
| Viral/ambiguous social post | Relevant customer/influencer personas | LLM-based |
| CEO public statement | Customers + influencers + journalists | Mixed |

Use deterministic rules for safety-critical triggers. Reserve LLM-based routing for genuinely ambiguous social cases.

---

## 6. Schemas built so far

### Customer Support ticket (see `Customer_Support_System/Customer_Support_Schema.md`)
- Core fields: `ticket_id`, `customer_id`, `status`, `priority`, `issue_type` (includes `safety_concern` as a distinct, escalation-worthy category), `description`, `linked_product_batch` (nullable — ties a complaint to a specific batch for recall/contamination tracing), `sentiment` (auto-scored via keyword matching, `sentiment_method` tags which scorer produced it, swappable later for an LLM-based one).
- **Ticket activity log:** a separate, append-only, generic log (`entity_type` + `entity_id` + `activity_type`) that records every change to a ticket. Deliberately generic so Social Network posts or other entities can log into the same table later without a schema change.
- Both the ticket and the log carry a `schema_version` field so future changes don't break old records.
- **Status: built and running.** API (5 endpoints), sentiment scorer, test suite, and a monitoring dashboard are all complete — see `Customer_Support_System/README.md` for how to run it.

### Not yet designed
- Social Network post/comment schema
- Event Generator's event schema (the crisis-trigger events — distinct from the ticket activity log above)

Agent persona prompt templates (`docs/`) **are** now wired to an LLM for both Customer and
Influencer agents — see `customer-agent/README.md` and `influencer-agent/README.md`.

---

## 7. Our 4-week schedule (+ 1 buffer week)

| Week | Focus |
|---|---|
| 1 | Design & foundations — schemas, persona attributes, API sketches (group session, then split) |
| 2 | Core systems build — Social Network + Customer Support APIs, persona prompt drafts, manual scenario tests |
| 3 | Agent intelligence — wire Customer/Influencer agents to an LLM, connect to real APIs, decision logging |
| 4 | Event generator + internal integration — routing logic, timed events, full internal scenario test, leakage check |
| 5 (buffer) | Cross-team integration — confirm contracts with Team 1 and Team 4, replace stubs with real calls, full end-to-end run, demo prep |

Work is split by **task type, not fixed lanes** — everyone touches both systems and agent work over the weeks, rotating who takes the more self-contained "solo" task each week versus the harder, fuzzier paired task.

---

## 8. Working principles (don't relitigate these per-task)

- **Schema before code.** Agree on the shape of a thing before building it — this is what let two people work in parallel without blocking each other.
- **Make new fields optional/nullable first.** Don't break existing data for a new feature; extend instead of rewriting.
- **Generic logs over bespoke ones.** One activity-log pattern, reused across entities, beats a new audit mechanism per feature.
- **Deterministic rules for safety-critical triggers; LLM judgment only for genuinely ambiguous cases.**
- **No agent gets privileged access** — not the CEO, not ours. Everything flows through systems.
- **Smaller and explicit beats bigger and clever.** Don't add infrastructure (separate services, queues, extra layers) unless the 4-week scope actually needs it now.

---

## 9. Running the whole project

Everything runs together with Docker Compose — one command starts every team's service.

### One-time setup
1. Install Docker Desktop if you don't have it.
2. Create a `.env` file at the repo root (copy `.env.example` if one exists). Empty is fine if you're not testing agents that need real API keys yet.

### Run everything
```bash
docker compose up --build
```

### What's running and where

| Service | What it is | URL |
|---|---|---|
| `customer-agent` | Customer agent (NAT + NeMo Guardrails, wired to a real NIM model). Served as an MCP tool, not REST — no browsable URL. See `customer-agent/README.md`. | MCP endpoint at `http://localhost:8001/mcp` (tool: `customer_agent_react`) |
| `influencer-agent` | Influencer agent (NAT-based, polls `social_network` and reacts). See `influencer-agent/README.md`. | http://localhost:8002/docs (NAT's own Swagger UI) |
| `customer-support-api` | Customer Support backend (FastAPI) | http://localhost:8003 (docs at `/docs`) |
| `customer-support-dashboard` | Customer Support monitoring UI | http://localhost:5173 |

Only rebuild the service you changed, instead of everything:
```bash
docker compose up --build customer-support-api
docker compose up --build customer-support-dashboard
```

If nothing changed since your last build, drop `--build` for a faster start:
```bash
docker compose up
```

See `Customer_Support_System/README.md` for details specific to that service (why there are two Dockerfiles, port choices, local-dev instructions without Docker).

---

## 10. Open items

- Confirm with Team 2 what their internal escalation/audit activity looks like, so naming (`actor` values, activity types) lines up across teams.
- Confirm with Team 4 whether their event engine expects a specific envelope format, so our event generator and activity log can feed into it without duplication.
- `customer-agent` and `influencer-agent` are both wired to a real LLM (NVIDIA NIM via NAT) as of Week 3 — see each service's own `README.md` for details. `influencer-agent` has a `poller.py` that autonomously watches `social_network` and reacts. `customer-agent` now has an equivalent: `driver.py`, started unconditionally by `main.py`, subscribes to the event-generator's `customer` tag over SSE and reacts once per persona to every event it sees. It remains invocable on demand as an MCP tool as well.
- `customer-agent`'s only outbound action is `create_ticket` against `customer-support-mcp` — **it does not post to `social_network`**. Its decision vocabulary includes `complain_on_social_media`, but nothing currently acts on that value. Posting to the platform is `influencer-agent`'s path only.
# bitrix-internal-actors

> Python multi-agent services simulating HappyTuna's internal org (COO, employees, internal chat,
> staff portal) with an immutable audit/replay log for reproducible AI-CEO crisis research.

This repository implements the **internal organization cluster** of the multi-agent
crisis-management research platform (BitriX world / HappyTuna case). It is **not** the research
subject — the CEO agent lives in a separate service and is the only agent under evaluation. This
repo produces the realistic, reproducible internal environment the CEO agent reacts to, plus the
audit trail researchers replay.

## Scope (what this repo owns)

| Component | Role | Status |
|-----------|------|--------|
| **Employee agents** (`services/employee`) | Workforce personas (QA, production, plant manager, concerned, whistleblower). Report issues, escalate concerns. | **Implemented** |
| **Internal Messaging** (`services/internal_messaging`) | Internal Messaging System — direct/group/incident chat + cross-channel activation firehose. REST `/api/*` + MCP `/mcp/chat`. | **Implemented** |
| **Coordinator** (`services/coordinator`) | Activation layer ("Director"): reads the cross-channel firehose and decides which agent wakes. Runs embedded in the employee worker. | **Implemented** |
| **COO agent** (`services/coo`) | Assesses operational impact, manages continuity, escalates beyond its authority, sends structured handoffs to the CEO. | *Placeholder — not yet implemented* |
| **Staff Portal** (`services/staff_portal`) | Employee Portal — announcements, morale/feedback indicators, directory. | *Placeholder — not yet implemented* |
| **Audit** (`services/audit`) | Immutable event log + deterministic replay for reproducibility. | *Placeholder — episodes are currently recorded per-employee in SQLite* |

**Out of scope:** the CEO agent, public-world actors (customers, journalists, regulators), the
scenario engine, and the CEO scorecard — owned by other teams. We integrate only through APIs and
the event broker.

## Tech stack

- Python 3.11+
- **LLM: Anthropic (Claude)** via an abstract client (`packages/llm/anthropic_client.py`).
  Default model `claude-haiku-4-5`; override with `EMPLOYEE_ANTHROPIC_MODEL`.
- **Durable state:** SQLite (zero-infra default) or PostgreSQL
- **Active state:** none (default) or Redis
- **Event bus:** none (default), Redis Streams, or Kafka (`confluent-kafka`)

An OpenAI-compatible client (`packages/llm/llm_client.py`) is also present for NVIDIA NIM
endpoints, but the employee agents run on Claude. A vector DB for semantic memory is planned;
employee memory is currently plain SQLite (`services/employee/domain/memory.py`).

## Getting started

Everything below runs with no infrastructure — SQLite store, no cache, no bus.

```bash
git clone <repo-url> bitrix-internal-actors
cd bitrix-internal-actors

python -m venv .venv
.venv/bin/pip install fastapi uvicorn pydantic pydantic-settings httpx pyyaml anthropic
# Windows: .venv\Scripts\pip install ...
```

Create a `.env` in the repo root:

```dotenv
# Required to run the employee agents (omit to run chat-only).
EMPLOYEE_ANTHROPIC_API_KEY=sk-ant-...
# Optional — defaults to claude-haiku-4-5.
# EMPLOYEE_ANTHROPIC_MODEL=claude-opus-4-8
```

### Run the world

```bash
.venv/bin/python scripts/run_local.py
```

This starts the Internal Messaging service on `http://localhost:8085`, seeds the `HT-2026-001`
incident channel, and launches the employee worker (which embeds the coordinator and polls the
activation firehose). Without an API key it runs chat-only. Ctrl+C stops everything.

Wake a persona by posting a message that mentions it — `run_local.py` prints the exact command
with the real channel id:

```bash
curl -X POST http://localhost:8085/api/channels/<CID>/messages \
  -H "Authorization: Bearer COO-1" -H "Content-Type: application/json" \
  -d '{"body":"status @EMP-QA-17"}'
```

You should see `[employee] EMP-QA-17 activated by CHAT_MESSAGE` followed by `acted → ...`.

### Full stack (PostgreSQL + Redis + Kafka)

Needs Docker. Brings the messaging service up in a container on port `8080`:

```bash
python scripts/run_local.py --full
```

### Tests

```bash
.venv/bin/pip install pytest pytest-asyncio
.venv/bin/python -m pytest -q
```

> **Note:** several `make` targets (`run-coo`, `run-employees`, `run-staff-portal`, `run-audit`,
> `migrate`) point at components that are not implemented yet and will fail. Use
> `scripts/run_local.py` as above.

## Layout

```text
packages/   shared libraries (agentkit, llm, mcp_core, schemas, eventbus, worldstate, common;
            authz and memory are empty placeholders)
services/   employee, internal_messaging, coordinator (implemented);
            coo, staff_portal, audit (placeholders)
scripts/    run_local.py — one command to run chat + seed + employee
docs/       architecture, agent profiles, technical designs, and the HappyTuna knowledge base
```

## Core rules

1. **No privileged access** — agents never see hidden ground truth, other agents' state, future events, or the live CEO score.
2. **Communicate through systems only** — via chat, portal, mail, and the event bus; never direct agent-to-agent calls.
3. **Everything is an event** — every state change is appended to the immutable audit log and is replayable from a seed.
4. **Authority is enforced** — tool calls pass identity → role permission → state check → audit. Enforced in code, not just the prompt: see `services/employee/domain/authority.py` and the `chat:system` gate in `services/internal_messaging/integration/identity.py`.
5. **Reproducibility first** — seeds, profiles, prompt/model/tool versions recorded per run.

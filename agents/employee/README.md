# Employee Agents

The workforce of HappyTuna: five Claude-driven personas (QA inspector, production
worker, plant manager, concerned employee, whistleblower) that live on the
**Internal Chat** platform and take **Customer Support** duty. One worker
process runs the whole population.

## How activation works

```
internal-chat firehose ──► coordinator (embedded) ──► wake the mentioned persona
customer-support queue ──► periodic sweep ──────────► wake one persona on duty
```

- **Chat mentions:** the worker embeds the coordinator, which polls the chat's
  cross-channel activation firehose (as `COORD-1`, a system identity that can
  read but not write). A message mentioning `@EMP-QA-17` wakes that persona; it
  perceives the channel's new messages and decides — via a ReAct loop on
  `claude-haiku-4-5` — whether and how to respond with its tools.
- **Support duty:** every `EMPLOYEE_SUPPORT_SWEEP_INTERVAL` seconds (default
  180, `0` disables) the worker checks the Customer Support queue. If open
  tickets exist, it wakes **one** support-capable persona (round-robin) to
  triage and respond. No tickets → no LLM call.

## Tools (authority-gated)

| Tool | Platform | Notes |
|---|---|---|
| `send_chat_message` | Internal Chat | Bearer identity = the persona's own id — a model can never impersonate a colleague |
| `list_open_tickets` | Customer Support | Read the open queue (compact triage view) |
| `respond_to_ticket` | Customer Support | Reply to the customer + set status (`in_progress`/`escalated`/`resolved`); `actor`/`assignee` forced to the persona's id |

Every tool sits behind the persona's authority policy
(`services/employee/domain/authority.py`): a channel the persona isn't
authorized for is denied in code, not just in the prompt.

## Personas

`services/employee/personas/*.yaml` — each defines identity, goal, backstory,
characteristics, authority (allowed actions + channels), and a whistleblower
tendency. All five currently act through `internal_messaging` and
`customer_support`.

## Memory

Each persona keeps durable SQLite memory (`/data/employee.db`): what it
observed, what it did (from the executor trace, not the model's claims), and
what was denied. Recent actions are recalled into the prompt so a persona
doesn't repeat itself.

## Running

Part of the unified compose:

```bash
docker compose up --build employee-agent          # needs ANTHROPIC_API_KEY in .env
```

Wake a persona by mentioning it in the seeded crisis channel (the CEO does
this on its own; you can too):

```bash
# find the channel id
curl -s http://localhost:8085/api/channels -H "Authorization: Bearer CEO-1"
# post a mention as the CEO
curl -s -X POST http://localhost:8085/api/channels/<CID>/messages \
  -H "Authorization: Bearer CEO-1" -H "Content-Type: application/json" \
  -d '{"body":"status update please @EMP-QA-17"}'

docker compose logs -f employee-agent
```

You should see `[employee] EMP-QA-17 activated by CHAT_MESSAGE` followed by
`acted → ...`. Support duty needs no trigger at all — file a ticket (or let the
customer agent do it) and the next sweep picks it up.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required** (or `EMPLOYEE_ANTHROPIC_API_KEY` for a dedicated key) |
| `EMPLOYEE_ANTHROPIC_MODEL` | `claude-haiku-4-5` | The personas' model |
| `EMPLOYEE_INTERNAL_MESSAGING_URL` | `http://localhost:8085` | Chat REST door (compose sets the docker-internal URL) |
| `EMPLOYEE_CUSTOMER_SUPPORT_URL` | `http://localhost:8003` | Support REST API |
| `EMPLOYEE_SUPPORT_SWEEP_INTERVAL` | `180` | Seconds between support sweeps (`0` = off) |
| `EMPLOYEE_POLL_INTERVAL` | `2.0` | Seconds between firehose polls |

## Layout

```
agents/employee/
├── packages/
│   ├── agentkit/        # shared ReAct engine, tool base, executor
│   └── llm/             # AnthropicClient (claude-haiku-4-5)
└── services/
    ├── coordinator/     # activation layer: firehose reader, routing rules, audit log
    └── employee/
        ├── agent/       # EmployeeAgent = persona + ReAct engine
        ├── app/         # Settings + worker entrypoint (python -m services.employee.app.main)
        ├── domain/      # authority gate, durable memory, perception
        ├── personas/    # the five persona YAMLs + loader
        ├── tools/       # chat adapter + customer-support tools
        └── worker/      # population builder, activation glue, support sweep
```

# Architecture

The HappyTuna simulation is a small world: **four platforms** every agent acts
through, **five LLM agents** that live on those platforms, and an **event
generator** that injects the crisis. Agents never talk to each other directly —
everything flows through platform APIs (REST or MCP), exactly like the real
company systems they model.

## The world at a glance

```mermaid
flowchart TB
    EG["Event generator<br/>scripted or LLM crisis feed<br/>(SSE, tags: customer / press)"]

    subgraph agents["Agents"]
        CU["Customer agent<br/>5 personas · Claude Haiku<br/>+ NeMo Guardrails"]
        IN["Influencer agent<br/>persona poller · Claude Haiku"]
        JO["Journalist agent<br/>ReAct · Claude Haiku<br/>Chroma RAG · Gemini embeddings"]
        EM["Employee agents<br/>5 personas · Claude Haiku"]
        CEO["CEO agent<br/>plan-solve + memory · Claude Haiku<br/>via MCP gateway"]
    end

    subgraph platforms["Platforms"]
        CS["Customer Support<br/>REST :8003 · MCP :8010<br/>+ dashboard :5173"]
        SN["Social Network 'BrightTweets'<br/>REST/UI :3005 · MCP /mcp/social + /mcp/analytics"]
        NW["Journalism site 'The Daily Catch'<br/>REST/UI :8004"]
        IC["Internal Chat<br/>REST :8085 · MCP :8090"]
    end

    EG -->|"tag: customer"| CU
    EG -->|"tag: press"| JO
    EG -->|"tag: press"| CEO

    CU -->|"create_ticket (MCP)"| CS
    CU -->|"create_post (MCP)"| SN
    IN <-->|"poll feed, comment, repost (REST)"| SN
    JO -->|"publish_article (REST)"| NW
    JO -->|"post_social (REST)"| SN
    EM <-->|"chat, mentions (REST)"| IC
    EM -->|"respond to tickets (REST)"| CS
    CEO -->|"support.* / social.* / analytics.* / chat.*<br/>(MCP gateway)"| CS
    CEO --> SN
    CEO --> IC
```

## How a crisis round unfolds

1. The **event generator** fires an event (`POST /replay` plays the scripted
   12-event salmonella arc; `POST /emit` injects one event; `generate()` is the
   LLM mode).
2. **Customer personas** (tag `customer`) react: file real support tickets,
   post complaints or praise on the social network, or quietly stop buying.
3. The **journalist** (tag `press`) investigates against its knowledge base,
   publishes an article on The Daily Catch, and shares the headline on the
   social network.
4. The **influencer** notices new posts on its poll cycle and amplifies or
   criticizes them.
5. The **CEO** (tag `press`, plus periodic reviews) reads the support queue,
   the analytics surface, the public feed and the internal chat — then acts:
   replies to tickets, posts public statements, convenes employees in chat.
6. **Employees** wake when mentioned in chat and on support-queue sweeps,
   report and escalate internally, and address customer complaints.
7. Reactions create new posts and tickets, which feed the next reactions —
   the cascade, not any single script, is the simulation.

## Communication contracts

| Producer → Consumer | Transport | Contract |
|---|---|---|
| Event generator → agents | SSE (`GET /subscribe?tag=`) | `{tag, text, seq, ts}` JSON frames; agents own a copy of `event_client.py` |
| Customer → Customer Support | MCP (streamable-http) | `create_ticket` |
| Customer → Social Network | MCP | `login` (per-session identity) then `create_post` |
| Influencer → Social Network | REST | `/api/auth/login`, feed paging, comments, reposts |
| Journalist → Journalism site | REST | `POST /articles` |
| Journalist → Social Network | REST | login + `POST /api/posts` |
| Employee → Internal Chat | REST | Bearer = agent id; mentions wake personas |
| Employee → Customer Support | REST | `GET /tickets?status=open`, `PATCH /tickets/{id}` |
| CEO → everything | MCP gateway | role-filtered tool surface, identity injected server-side, full audit log (see [ceo-agent.md](ceo-agent.md)) |

## LLM usage (all deliberately small/fast models)

On the **`stable-release`** branch every agent runs the same model, so a run
depends on exactly one provider. (`main` keeps the original mixed roster: NIM for
the customer and influencer agents, Gemini for the journalist and CEO.)

| Component | Provider · model | Used for |
|---|---|---|
| Customer agent | Anthropic · `claude-haiku-4-5` (via NeMo Guardrails) | persona decisions |
| Influencer agent | Anthropic · `claude-haiku-4-5` | amplify/criticize/ignore decisions |
| Journalist agent | Anthropic · `claude-haiku-4-5` | ReAct loop |
| Journalist embeddings | Gemini · `gemini-embedding-001` | RAG knowledge base — Anthropic has no embeddings API |
| CEO agent | Anthropic · `claude-haiku-4-5` | planning, execution, summaries, memory folding |
| Employee agents | Anthropic · `claude-haiku-4-5` | persona ReAct cycles |
| Event generator | Anthropic · `claude-haiku-4-5` | optional LLM feed mode (`/replay` needs no LLM) |
| Social network analytics | Anthropic · `claude-haiku-4-5` | optional AI sentiment (off by default) |

Two agents reach Anthropic through its **OpenAI-compatible endpoint**
(`https://api.anthropic.com/v1/`) rather than a native client, because their
frameworks only speak the OpenAI wire format: NeMo Guardrails' default LLM path
(customer agent) and NAT, which ships no Anthropic LLM type (influencer). Neither
needed a new dependency as a result. The journalist, CEO, and employees use
native Anthropic clients.

Providers stay swappable without touching agent logic: the customer agent
through `CUSTOMER_LLM_*` in `.env` (patched into the guardrails config at load
time), the influencer through `NAT_CONFIG_FILE` (one of the `configs/` files).

## Isolation rules (inherited from the original research design)

- **No privileged access:** no agent sees another agent's internal state,
  ground truth, or future events — only what the platforms expose.
- **Identity is never an argument:** every platform binds the caller's
  identity at the connection/session layer (Bearer token, MCP session login),
  so a model cannot impersonate another agent by crafting tool arguments.
- **The CEO cannot manufacture its own public** (no ticket creation, no
  analytics controls) — enforced in the gateway's role policy, not just in
  prompts.

---

# Running it

## State: what a run starts from

```bash
docker compose down && docker compose up --build   # fresh, empty world
```

| Store | Lives in | Reset by |
|---|---|---|
| Social feed (BrightTweets) | the container's own filesystem | any recreate of `social-network` — every run starts from an empty feed |
| Influencer feed cursors | the container's own filesystem | any recreate — the ids only mean something to one social DB |
| Tickets, articles, chat history, CEO memory | named volumes | `docker compose down -v` |

The public feed is deliberately the volatile one: it is the simulation's visible
output, so a run should start blank and contain only what the agents wrote.
`SEED_DB=true` loads the demo crisis arc instead.

The flip side of that: the feed lives and dies with its container, and
`docker compose up --build <agent>` rebuilds that agent's *dependencies* too —
which recreates the social network and clears the feed mid-run. To restart one
agent without touching the world it lives in:

```bash
docker compose up -d --no-deps --build customer-agent
```

## When an agent isn't reacting

The platforms are plain web services — if a page loads, that half works. Agents
only ever fail for two reasons: they never got the event, or their model
provider didn't answer.

```bash
docker compose logs --tail 30 customer-agent   # one line per persona per event
curl -s localhost:8006/health                  # is the feed alive?
```

**"got no decision: ... the model provider did not answer"** — the provider is
down, throttling you, or the key is wrong; it isn't the agent. On this branch
every agent shares one provider, so this either affects all five at once or
none. Probe it directly — the same endpoint the customer and influencer agents
use, so a `200` here rules the provider out entirely:

```bash
curl -m 60 -X POST https://api.anthropic.com/v1/chat/completions \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}'
```

A `401` means the key; a `429` means rate limits (agents retry, but a whole
`/replay` arriving at once is a burst — use `/emit` instead); a hang means
Anthropic. Only the journalist has a second dependency: its knowledge-base
embeddings go to Gemini, so a Gemini outage stops the journalist at boot while
everyone else keeps running.

To move an agent to a different provider, see the `CUSTOMER_LLM_*` override
block in `.env.example` (customer) and the `configs/` files selected by
`NAT_CONFIG_FILE` (influencer) — neither requires touching agent code.

## Keeping LLM costs down

- The scripted feed (`POST /replay`) costs nothing to generate; agent
  reactions are the only LLM spend, and every agent runs a small model.
- `AI_ANALYSIS_ENABLED=false` (default) keeps social-network sentiment on a
  free lexicon scorer.
- `CEO_DRY_RUN=true` lets the CEO observe and reason without writing anywhere.
- `CEO_REVIEW_INTERVAL=0` and `EMPLOYEE_SUPPORT_SWEEP_INTERVAL=0` turn off the
  periodic (token-spending) wake-ups; agents then act only on events.
- Run a single event instead of a replay:
  `curl -X POST http://localhost:8006/emit -H "Content-Type: application/json" -d '{"tag":"press","text":"..."}'`

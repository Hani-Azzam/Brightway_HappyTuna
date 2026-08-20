# HappyTuna — a multi-agent crisis simulation

> [!CAUTION]
> **All NIM Ollama model servers will be deprecated on 25.08.2026.** The customer
> and influencer agents run on NVIDIA NIM — see
> [When an agent isn't reacting](#when-an-agent-isnt-reacting) to repoint them at
> another provider.

A simulated world around **HappyTuna**, a fictional canned-tuna company going
through a food-safety crisis. LLM-driven agents — customers, an influencer, a
journalist, employees, and a CEO — live on realistic company platforms
(customer support, a social network, a journalism site, an internal chat) and
react to crisis events injected by an event generator. The cascade of their
reactions *is* the simulation: complaints become tickets, tickets become
posts, posts become news, and the CEO has to manage all of it.

## Quick start

Prerequisites: Docker Desktop (with Compose).

```bash
git clone <this-repo>
cd Brightway_HappyTuna

cp .env.example .env        # then fill in the LLM keys (see below)

docker compose up --build   # first build takes a while (agent images)
```

Then kick off the crisis and watch the world react:

```bash
# play the scripted 12-event salmonella arc (2s between events)
curl -X POST "http://localhost:8006/replay?delay=2.0"

docker compose logs -f customer-agent journalist-agent ceo-agent
```

### Where to look

| URL | What you'll see |
|---|---|
| http://localhost:3005/app/ | **BrightTweets** — the social network: customer complaints, influencer takes, journalist headlines, CEO statements |
| http://localhost:8004 | **The Daily Catch** — the journalism site's live front page |
| http://localhost:5173 | **Customer-support dashboard** — tickets arriving and being handled |
| http://localhost:8003/docs | Customer Support API |
| http://localhost:8085/health | Internal chat (REST; agents-only, no UI) |
| http://localhost:8006/health | Event generator |

### API keys (.env)

| Key | Used by | Get one at |
|---|---|---|
| `NVIDIA_API_KEY` | customer agent, influencer agent, event generator (all `llama-3.1-8b`) | https://build.nvidia.com |
| `GEMINI_API_KEY` | journalist + CEO (`gemini-2.5-flash-lite`) | https://aistudio.google.com |
| `ANTHROPIC_API_KEY` | employee agents (`claude-haiku-4-5`) | https://console.anthropic.com |

A missing key doesn't break the stack — the agents that need it will just fail
when they try to think. Everything runs on deliberately small, fast models.

### Resetting the world

The social network starts **empty** and is wiped whenever its container is
recreated, so every run begins from a blank public feed and everything you see
on it was written by an agent:

```bash
docker compose down && docker compose up --build   # fresh, empty world
```

It has no Docker volume on purpose (nor does the influencer, whose state is
just "last social post I saw"). `SEED_DB=true` in `.env` loads the demo crisis
arc instead of starting empty. Everything else — tickets, articles, chat
history, CEO memory — *does* keep a volume and survives `down`; add `-v` to
reset those too.

| State | Survives `down`? |
|---|---|
| Social feed (posts, users, likes) | no — always rebuilt empty |
| Influencer feed cursors | no — they only mean something to one social DB |
| Tickets, articles, chat, CEO memory | yes (`docker compose down -v` clears them) |

The flip side: the feed lives and dies with its container, and `docker compose
up --build <agent>` rebuilds that agent's *dependencies* too — which recreates
the social network and clears the feed mid-run. To restart one agent without
touching the world it lives in:

```bash
docker compose up -d --no-deps --build customer-agent
```

## The world

```
 event generator ──crisis events──►  agents  ──act through──►  platforms
                                       ▲                          │
                                       └───────── react to ◄──────┘
```

**Platforms** ([`platforms/`](platforms/)):

| Platform | What it is |
|---|---|
| [`customer-support`](platforms/customer-support/) | Ticketing system — REST + MCP + monitoring dashboard |
| [`social-network`](platforms/social-network/) | "BrightTweets", a Twitter-like platform — UI, REST, and MCP servers (social + analytics) |
| [`journalism-site`](platforms/journalism-site/) | "The Daily Catch" news site — REST + live front page |
| [`internal-chat`](platforms/internal-chat/) | Company messaging — REST + MCP, with mention-based agent activation |

**Agents** ([`agents/`](agents/)):

| Agent | What it does |
|---|---|
| [`customer`](agents/customer/) | 5 personas react to events: file real support tickets, post complaints/praise on the social network |
| [`influencer`](agents/influencer/) | Polls the social feed and amplifies or criticizes what it sees |
| [`journalist`](agents/journalist/) | Investigates press events (RAG knowledge base), publishes articles, shares headlines |
| [`employee`](agents/employee/) | 5 personas wake on chat mentions and support-queue sweeps; report, escalate, answer complaints |
| [`ceo`](agents/ceo/) | The centerpiece: plan-solve loop with sliding-window memory, acting on **all** platforms through a policy-enforcing MCP gateway |

**Event generator** ([`event-generator/`](event-generator/)): fires the crisis
feed over SSE — scripted (`/replay`, free and deterministic) or LLM-generated.

## Documentation

The [`docs/`](docs/) directory is the documentation hub:

- [`docs/architecture.md`](docs/architecture.md) — the whole world on one page (diagrams, contracts, LLM table)
- [`docs/ceo-agent.md`](docs/ceo-agent.md) — the CEO agent in depth (gateway, memory, cycle diagrams)
- [`docs/README.md`](docs/README.md) — index of every document in the repo

Each platform and agent also keeps its own README next to its code.

## Repository layout

```
├── agents/            # customer, influencer, journalist, employee, ceo
├── platforms/         # customer-support, social-network, journalism-site, internal-chat
├── event-generator/   # the crisis feed
├── docs/              # documentation hub
├── docker-compose.yml # the entire world, one command
├── .env.example       # single global env file (copy to .env)
└── README.md
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
down or throttling you, not the agent. NVIDIA's shared endpoint is the usual
suspect; its signature is a request that hangs ~300s and then returns
`HTTP 504` with `Nvcf-Status: errored`, while `GET /v1/models` still answers
instantly:

```bash
curl -m 60 -X POST https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Authorization: Bearer $NVIDIA_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"meta/llama-3.1-8b-instruct","messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}'
```

The customer and influencer agents are the two on NIM. To keep demoing while
it's degraded, uncomment the **NIM outage escape hatch** block in `.env` — it
repoints both at Gemini's OpenAI-compatible endpoint with the key you already
have — then:

```bash
docker compose up -d --no-deps customer-agent influencer-agent
```

Comment it back out to return to NIM; nothing else in the project changes.

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

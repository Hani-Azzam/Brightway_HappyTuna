# HappyTuna — a multi-agent crisis simulation

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

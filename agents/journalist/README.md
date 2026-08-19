# Journalist Agent

An autonomous AI journalist working for **The Daily Catch** (the journalism
site platform). It listens to `press` events from the event generator,
investigates each one against a Chroma-backed knowledge base, publishes an
article on the journalism site, and shares the headline on the social network.

Built on a LangChain ReAct loop (`base/tool_agent.py`) with Gemini
(`gemini-2.5-flash-lite`) and RAG over the bundled `knowledge/` docs.

## Personality

| Trait | Value |
|---|---|
| Bias | Neutral |
| Investigative depth | High |
| Verification strictness | High |
| Sensationalism | Low |
| Credibility | High |

## Agent flow

```
Event generator fires a "press" event
        ↓
1. search_knowledge  →  query Chroma for background context
        ↓
2. search_news       →  check if The Daily Catch already covered it
        ↓
3. publish_article   →  POST the finished article to The Daily Catch
        ↓
4. post_social       →  share the headline on BrightTweets
        ↓
   ...waits for the next event
```

## Tools

| Tool | System | Description |
|---|---|---|
| `search_knowledge` | Chroma (embedded) | Background research via RAG |
| `search_news` | Journalism site | Check existing coverage |
| `publish_article` | Journalism site | Publish the article |
| `post_social` | Social network | Share the headline |

### Knowledge base (indexed at startup)

| File | Content |
|---|---|
| `knowledge/crisis_management_theory.txt` | Coombs framework, SCCT, case studies |
| `knowledge/food_recall_procedures.txt` | Recall classes, legal obligations, salmonella facts |
| `knowledge/happytuna_background.txt` | Company history, production lines |
| `knowledge/happytuna_world_reference.txt` | The simulated world's agents and systems |

The Chroma store is **embedded** (persist directory inside the container) —
no separate vector-DB server. Knowledge is re-indexed on each container start.

## How to run

Everything is part of the unified compose at the repo root:

```bash
# from the repo root — .env needs GEMINI_API_KEY
docker compose up --build journalist-agent
```

That also starts what it needs (`event-generator`, `journalism-site`,
`social-network`). Then fire an event and watch it work:

```bash
# a single press event…
curl -X POST http://localhost:8006/emit \
  -H "Content-Type: application/json" \
  -d '{"tag":"press","text":"HappyTuna salmonella cluster confirmed - 3 consumers hospitalized"}'

# …or the full scripted crisis feed (12 events, 6 of them press)
curl -X POST "http://localhost:8006/replay?delay=2.0"

docker compose logs -f journalist-agent
```

Published articles appear at **http://localhost:8004** (The Daily Catch UI)
and the shared headlines at **http://localhost:3005/app/** (BrightTweets).

### Running locally without Docker

```bash
cd agents/journalist
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt

export GEMINI_API_KEY=...                        # required
export EVENT_GENERATOR_URL=http://localhost:8006
export NEWS_URL=http://localhost:8004
export SOCIAL_URL=http://localhost:3005
export CHROMA_PERSIST_DIR=./.chroma

python listener.py        # event-driven (production behavior)
python main.py            # interactive: type events yourself
```

(The platforms must already be up: `docker compose up -d event-generator
journalism-site social-network`.)

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** The agent's LLM + embeddings |
| `JOURNALIST_MODEL` | `gemini-2.5-flash-lite` | Chat model |
| `JOURNALIST_TEMPERATURE` | `0.2` | Low = factual |
| `JOURNALIST_MAX_STEPS` | `12` | ReAct step budget |
| `EVENT_GENERATOR_URL` | `http://localhost:8006` | Press feed (compose sets the docker-internal URL) |
| `NEWS_URL` | `http://localhost:8003` | Journalism site API |
| `SOCIAL_URL` | `http://localhost:3005` | Social network API |
| `CHROMA_PERSIST_DIR` | `/data/chroma` | Embedded Chroma location |

## Layout

```
agents/journalist/
├── listener.py          # event-driven entrypoint (container CMD)
├── main.py              # interactive entrypoint for local testing
├── journalist_agent.py  # agent assembly: LLM + RAG + tools + ReAct config
├── prompts.py           # system hint (personality, publishing rules)
├── event_client.py      # SSE client (copied from event-generator, by design)
├── tools/               # publish_article, search_news, search_knowledge, post_social
├── knowledge/           # the RAG corpus
├── base/                # shared ReAct engine + tool/agent interfaces
└── services/            # Gemini client, tool executor, embeddings, Chroma store, RAG
```

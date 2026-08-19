# BitriX — HappyTuna Crisis Simulation

Agentic AI course project. An AI agent acts as CEO of HappyTuna — a fictional $250M canned tuna company — and must manage a salmonella crisis in one of its production lines.

This repository belongs to **Team 4** and contains:
- **Journalist Agent** — investigates and publishes news (LangChain + Chroma DB) ✅
- **Regulator Agent** — enforces food safety laws — coming soon
- **NTP System** — shared simulation clock for all agents ✅
- **News Website** — The Daily Catch, external news feed ✅

---

## What Other Teams Need From Us

> If you are on another team, here is exactly what to call and how.

| What we provide | Docker URL | Local URL | Who needs it |
|---|---|---|---|
| NTP — simulation clock | `http://ntp:8001` | `http://localhost:8001` | **ALL teams** |
| News Website API | `http://news-website:8003` | `http://localhost:8003` | **ALL teams** |

### Calling NTP from your agent
```python
import httpx

def get_sim_time() -> str:
    try:
        r = httpx.get("http://ntp:8001/time", timeout=3)  # use localhost:8001 locally
        return r.json()["sim_time"]
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
```

### Reading the News Website from your agent
```python
import httpx

# Get latest headlines
r = httpx.get("http://news-website:8003/feed", params={"limit": 10})
headlines = r.json()

# Search by keyword
r = httpx.get("http://news-website:8003/articles/search", params={"q": "salmonella"})
articles = r.json()
```

### Publishing to the News Website (Journalist agent only)
```python
import httpx

httpx.post("http://news-website:8003/articles", json={
    "title": "BREAKING: Salmonella detected at HappyTuna Production Line A",
    "body": "Full article text...",
    "author": "Journalist Agent",
    "category": "breaking",   # breaking | investigative | update | opinion
    "tags": ["HappyTuna", "salmonella", "recall"],
    "source_urls": []
})
```

---

## Quick Start

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd bitrx

# 2. Copy and fill in your API keys
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY

# 3. Start all systems
docker compose up --build ntp news-website chroma

# 4. In a second terminal — start the event generator (other team's repo)
cd customer-influencer-agents
docker compose up event-generator

# 5. In a third terminal — run the journalist listener
cd bitrx
py -m agents.journalist.listener
```

---

## Services

| Service | Local URL | Docker URL | Description |
|---|---|---|---|
| NTP | http://localhost:8001 | http://ntp:8001 | Simulation clock |
| News Website | http://localhost:8003 | http://news-website:8003 | The Daily Catch news feed |
| Chroma DB | http://localhost:8000 | http://chroma:8000 | Agent RAG memory |
| Event Generator | http://localhost:8006 | http://event-generator:8000 | Crisis event feed (other team) |
| BrightTweets | http://localhost:3005 | http://social-network:3005 | Social network (other team) |
| Email | http://localhost:8010 | http://email:8010 | Email system (other team) |

### Quick health checks
```
http://localhost:8001/time              → NTP current sim time
http://localhost:8001/docs             → NTP API docs
http://localhost:8003                  → The Daily Catch news site
http://localhost:8003/docs             → News Website API docs
http://localhost:8000/api/v2/heartbeat → Chroma DB health
http://localhost:8006/health           → Event generator health
```

---

## 1. NTP — Simulation Time Service

A shared clock for the entire BitriX world. All agents use this instead of real system time.

### Time model

| Setting | Value |
|---|---|
| Speed | 60× real time |
| 1 real minute | = 1 simulated hour |
| 1 real hour | = 1 simulated day |
| Sim start | Monday 10 June 2024, 08:00 UTC |
| Port | 8001 |

### API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/time` | Current simulated timestamp |
| GET | `/time/info` | Full sim metadata + elapsed time |
| POST | `/time/advance` | Jump clock forward manually |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive Swagger docs |

### GET /time — example response
```json
{
  "sim_time": "2024-06-10T09:23:00+00:00",
  "sim_time_human": "Monday, 10 June 2024 09:23:00 UTC",
  "real_time": "2026-06-28T10:01:00+00:00",
  "day_of_week": "Monday",
  "speed_multiplier": 60.0
}
```

### Advance time for testing
```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8001/time/advance" `
  -ContentType "application/json" `
  -Body '{"seconds": 86400}'
```

---

## 2. News Website — The Daily Catch

An external news site where the Journalist agent publishes articles. All agents monitor this feed to track how the crisis is developing.

### Port: 8003 | Web UI: http://localhost:8003

### API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/articles` | List articles (?category=, ?tag=, ?limit=) |
| GET | `/articles/search?q=` | Search by keyword |
| GET | `/articles/{id}` | Get single full article |
| GET | `/feed` | Lightweight headlines only |
| POST | `/articles` | Publish a new article |
| GET | `/health` | Health check |
| GET | `/docs` | Interactive Swagger docs |

### Article categories

| Category | Description |
|---|---|
| `breaking` | Urgent event, public safety at risk — red ticker |
| `investigative` | Deep research, multiple sources |
| `update` | Follow-up to existing story |
| `opinion` | Editorial analysis |

### POST /articles — request body
```json
{
  "title": "string (required)",
  "body": "string (required)",
  "author": "string (required)",
  "category": "breaking | investigative | update | opinion",
  "tags": ["HappyTuna", "salmonella"],
  "source_urls": []
}
```

### Web UI features
- Live article feed with category badges
- Breaking news ticker when breaking articles exist
- Search and category filters
- Click any article to read full content
- Sidebar stats and most viewed
- Auto-refreshes every 15 seconds
- Simulation clock display

### Delete an article (admin/testing)
```bash
docker exec -it bitrx-news python3 -c "
import sqlite3
conn = sqlite3.connect('/data/news.db')
conn.execute(\"DELETE FROM articles WHERE title LIKE '%keyword%'\")
conn.commit()
print('Deleted:', conn.execute('SELECT changes()').fetchone()[0], 'rows')
conn.close()
"
```

---

## 3. Journalist Agent

An autonomous AI agent that investigates crisis events and publishes news to The Daily Catch. Built on **LangChain** using a **ReAct** loop with **Chroma DB** for background knowledge. Listens to the event generator for incoming press events automatically.

### Personality

| Trait | Value |
|---|---|
| Bias | Neutral |
| Investigative Depth | High |
| Verification Strictness | High |
| Sensationalism | Low |
| Public Interest Focus | High |
| Speed of Publication | Moderate |
| Credibility | High |

### Agent flow

```
Event Generator fires a "press" event
        ↓
1. search_knowledge  →  Query Chroma DB for background context
        ↓
2. search_news       →  Check if story already covered on The Daily Catch
        ↓
3. send_email        →  Contact sources (CEO, COO, Regulator) for comment
        ↓
4. read_email        →  Check inbox for replies from sources
        ↓
5. publish_article   →  POST finished article to The Daily Catch
        ↓
6. post_social       →  Share headline on BrightTweets
        ↓
7. final_answer      →  Waits for next event...
```

### Tools

| Tool | System | Description |
|---|---|---|
| `search_knowledge` | Chroma DB | Find background via RAG |
| `search_news` | News Website | Check existing coverage |
| `send_email` | Email (other team) | Contact sources |
| `read_email` | Email (other team) | Read replies |
| `publish_article` | News Website | Publish article |
| `post_social` | BrightTweets (other team) | Share on social |

### Chroma DB knowledge base (pre-loaded on startup)

| File | Content |
|---|---|
| `crisis_management_theory.txt` | Coombs framework, SCCT, Boeing/Coca-Cola cases |
| `food_recall_procedures.txt` | Recall classes, legal obligations, salmonella facts |
| `happytuna_background.txt` | Company history, executives, production lines |
| `happytuna_world_reference.txt` | All agents, all systems, crisis scenario |

### How to run

```bash
# Terminal 1 — start Docker systems
docker compose up ntp news-website chroma

# Terminal 2 — start event generator (other team's repo)
cd customer-influencer-agents
docker compose up event-generator

# Terminal 3 — start journalist listener
cd bitrx
py -m agents.journalist.listener
```

### Fire a test event
```cmd
# Inject a single event
curl -X POST http://localhost:8006/emit -H "Content-Type: application/json" -d "{\"tag\":\"press\",\"text\":\"HappyTuna salmonella confirmed - 3 consumers hospitalized\"}"

# Or run the full scripted feed (5 events, Day 1 to Day 10)
curl -X POST http://localhost:8006/replay
```

---

## 4. Regulator Agent

Enforces food safety laws, opens investigations, issues fines. Built on **NeMo + Chroma DB**.

Coming soon.

---

## Environment Variables

Copy `.env.example` to `.env`:

```dotenv
# Required
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001

# Local development (outside Docker)
NTP_URL=http://localhost:8001
NEWS_URL=http://localhost:8003
NEWS_PUBLIC_URL=http://localhost:8003
CHROMA_HOST=localhost
CHROMA_PORT=8000
SOCIAL_URL=http://localhost:3005
EMAIL_URL=http://localhost:8010
EVENT_GENERATOR_URL=http://localhost:8006

# Docker (uncomment when running agents inside containers)
# NTP_URL=http://ntp:8001
# NEWS_URL=http://news-website:8003
# CHROMA_HOST=chroma
# SOCIAL_URL=http://social-network:3005
# EMAIL_URL=http://email:8010
# EVENT_GENERATOR_URL=http://event-generator:8000

# Journalist agent
JOURNALIST_MODEL=gemini-2.5-flash
JOURNALIST_TEMPERATURE=0.2
JOURNALIST_MAX_STEPS=12


# Regulator agent (coming soon)
# REGULATOR_MODEL=gemini-2.5-flash
# REGULATOR_TEMPERATURE=0.1
# REGULATOR_MAX_STEPS=10
```

---

## Project Structure

```
bitrx/
├── base/
│   ├── agent_base.py        # Abstract agent interface
│   ├── tool_base.py         # Abstract tool interface
│   ├── tool_agent.py        # ReAct loop engine
│   ├── memory_base.py       # Abstract memory interface
│   └── retriever_base.py    # Abstract retriever interface
│
├── services/
│   ├── llm_client.py        # Google Gemini LLM wrapper
│   ├── tool_executor.py     # Tool runner with retry + tracing
│   ├── embedding_service.py # Google embedding model
│   ├── document_store.py    # Chroma DB document store
│   ├── rag_pipeline.py      # RAG pipeline
│   └── vector_memory_store.py
│
├── agents/
│   ├── journalist/
│   │   ├── journalist_agent.py
│   │   ├── prompts.py
│   │   ├── main.py          # Manual run (for testing)
│   │   ├── listener.py      # Event-driven run (production)
│   │   ├── event_client.py  # SSE client from event generator team
│   │   ├── requirements.txt
│   │   ├── Dockerfile
│   │   ├── knowledge/
│   │   │   ├── crisis_management_theory.txt
│   │   │   ├── food_recall_procedures.txt
│   │   │   ├── happytuna_background.txt
│   │   │   └── happytuna_world_reference.txt
│   │   └── tools/
│   │       ├── publish_article.py
│   │       ├── search_news.py
│   │       ├── search_knowledge.py
│   │       ├── send_email.py
│   │       ├── read_email.py
│   │       └── post_social.py
│   └── regulator/           # Coming soon
│
├── systems/
│   ├── ntp/                 # Simulation clock — FastAPI
│   └── news-website/        # The Daily Catch — FastAPI + SQLite
│
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Journalist agent | LangChain, ReAct loop |
| Board agent | LangChain (under development) |
| Regulator agent | NeMo (coming soon) |
| LLM | Google Gemini 2.5 Flash |
| Embeddings | Google text-embedding-004 |
| Vector DB | Chroma DB |
| Systems | FastAPI + SQLite |
| Containerization | Docker + docker-compose |
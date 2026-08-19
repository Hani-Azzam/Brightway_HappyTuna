# News Website — BitriX Simulation

The external news channel for the HappyTuna crisis simulation. The Journalist agent publishes articles here, and all other agents (Regulator, Board, Customer, Influencer) monitor it to stay informed about how the crisis is unfolding.

Think of it as **ynet** — a public news site that exists inside the simulation world.

---

## What it does

- Stores and serves news articles published by the Journalist agent
- Provides a live web UI that auto-refreshes every 15 seconds
- Stamps every article with **simulated time** from the NTP service
- Lets other agents search and filter articles by keyword, category, or tag

---

## Running locally

```bash
# With Docker Compose (recommended — also starts NTP)
docker compose up --build news-website ntp

# Then open the news site in your browser
http://localhost:8003
```

---

## Environment variables

| Variable  | Default           | Description                       |
| --------- | ----------------- | --------------------------------- |
| `NTP_URL` | `http://ntp:8001` | Where to get simulated timestamps |
| `DB_PATH` | `/data/news.db`   | SQLite database file path         |

Set these in `docker-compose.yml` or your `.env` file.

---

## API reference

### `GET /articles`

List all articles, newest first.

**Query parameters:**
| Param | Type | Description |
|---|---|---|
| `category` | string | Filter by category (`breaking`, `investigative`, `update`, `opinion`) |
| `tag` | string | Filter by tag (e.g. `salmonella`) |
| `limit` | int | Max results, default 20, max 100 |

**Example:**

```bash
GET http://localhost:8003/articles?category=breaking&limit=5
```

**Response:**

```json
[
  {
    "id": "a3f2...",
    "title": "HappyTuna under scrutiny as salmonella fears grow",
    "body": "Sources close to the production facility...",
    "author": "Journalist Agent",
    "category": "breaking",
    "tags": ["HappyTuna", "salmonella", "recall"],
    "published_at": "2024-06-10T14:30:00+00:00",
    "created_at": "2026-06-28T10:01:00+00:00",
    "views": 12,
    "source_urls": []
  }
]
```

---

### `GET /articles/{id}`

Get a single article by its ID. Also increments the view counter by 1.

```bash
GET http://localhost:8003/articles/a3f2c1d4-...
```

---

### `GET /articles/search?q=`

Search articles by keyword in title and body.

```bash
GET http://localhost:8003/articles/search?q=salmonella
```

---

### `GET /feed`

Lightweight feed — returns only `id`, `title`, `author`, `category`, `tags`, `published_at`. Used by agents that just need to monitor headlines without downloading full article bodies.

```bash
GET http://localhost:8003/feed?limit=10
```

---

### `POST /articles`

Publish a new article. Called by the Journalist agent.

**Request body:**

```json
{
  "title": "HappyTuna under scrutiny as salmonella fears grow",
  "body": "Full article text goes here...",
  "author": "Journalist Agent",
  "category": "breaking",
  "tags": ["HappyTuna", "salmonella", "recall"],
  "source_urls": ["http://company-website:8005/statements/1"]
}
```

**Fields:**
| Field | Required | Description |
|---|---|---|
| `title` | yes | Article headline |
| `body` | yes | Full article text |
| `author` | yes | Who published it (agent name or ID) |
| `category` | no | `breaking` / `investigative` / `update` / `opinion` — default `update` |
| `tags` | no | List of keyword tags |
| `source_urls` | no | Links the journalist investigated |

**Response:**

```json
{
  "id": "a3f2c1d4-...",
  "title": "HappyTuna under scrutiny as salmonella fears grow",
  "published_at": "2024-06-10T14:30:00+00:00",
  "message": "Article published successfully"
}
```

> The `published_at` timestamp is automatically pulled from the NTP service — agents do not need to supply it.

---

### `GET /health`

Health check — returns 200 if the service is running.

```json
{ "status": "ok", "service": "news-website" }
```

---

### `GET /time-proxy`

Proxies the NTP `/time` response for the browser UI. Agents should call NTP directly — this endpoint exists only for the frontend.

---

## Article categories

| Category        | When to use                                             |
| --------------- | ------------------------------------------------------- |
| `breaking`      | Urgent, unfolding news — triggers the red ticker banner |
| `investigative` | Deep research pieces with sources and background        |
| `update`        | Follow-up to an existing story                          |
| `opinion`       | Editorial or analysis piece                             |

---

## Database

SQLite file at `/data/news.db` (mounted as a Docker volume — data persists across container restarts).

**Articles table:**

| Column         | Type    | Description                            |
| -------------- | ------- | -------------------------------------- |
| `id`           | TEXT    | UUID, auto-generated                   |
| `title`        | TEXT    | Article headline                       |
| `body`         | TEXT    | Full article content                   |
| `author`       | TEXT    | Agent name or ID                       |
| `category`     | TEXT    | One of the 4 categories above          |
| `tags`         | TEXT    | JSON array of strings                  |
| `published_at` | TEXT    | Simulated time (ISO 8601) from NTP     |
| `created_at`   | TEXT    | Real wall-clock time (ISO 8601)        |
| `views`        | INTEGER | Incremented on each GET /articles/:id  |
| `source_urls`  | TEXT    | JSON array of URLs the journalist used |

On first startup, 3 seed articles are inserted automatically so the simulation world has background news before the crisis begins.

---

## How agents should use this

### Journalist agent — publishing an article

```python
import httpx

def publish_article(title, body, category, tags):
    r = httpx.post("http://news-website:8003/articles", json={
        "title": title,
        "body": body,
        "author": "journalist-agent",
        "category": category,
        "tags": tags,
    })
    return r.json()  # returns id and published_at
```

### Regulator / Board / Customer agent — monitoring the news

```python
import httpx

def check_for_crisis_news():
    r = httpx.get("http://news-website:8003/articles/search", params={"q": "salmonella"})
    articles = r.json()
    return articles  # list of matching articles

def get_latest_headlines():
    r = httpx.get("http://news-website:8003/feed", params={"limit": 5})
    return r.json()
```

---

## File structure

```
systems/news-website/
├── main.py           # FastAPI backend — all endpoints, DB, NTP integration
├── ui.html           # Frontend — the live news site UI
├── Dockerfile        # Container build instructions
└── requirements.txt  # Python dependencies
```

## Dependencies

- `fastapi` — web framework
- `uvicorn` — ASGI server
- `pydantic` — request validation
- `httpx` — HTTP client (for calling NTP)
- `sqlite3` — built into Python, no install needed

---

## Notes

- The News Website **depends on NTP** — it calls NTP to timestamp articles. If NTP is down, it falls back to real time.
- All agents communicate with this service over the `bitrx` Docker network using the hostname `news-website` and port `8003`.
- The web UI auto-refreshes every 15 seconds — you can watch articles appear in real time during the simulation without manual refresh.

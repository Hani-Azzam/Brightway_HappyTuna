from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import httpx
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

app = FastAPI(title="The Daily Catch", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.getenv("DB_PATH", "/data/news.db")
NTP_URL = os.getenv("NTP_URL", "http://ntp:8001")


# --- DB setup ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'update',
            tags TEXT NOT NULL DEFAULT '[]',
            published_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            views INTEGER NOT NULL DEFAULT 0,
            source_urls TEXT NOT NULL DEFAULT '[]'
        )
    """)
    conn.commit()

    # Seed background articles if empty
    count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    if count == 0:
        seed_articles = [
            {
                "id": str(uuid.uuid4()),
                "title": "HappyTuna expands production capacity with new Line B facility",
                "body": "HappyTuna, one of Israel's leading canned tuna producers, announced this week the completion of its new Production Line B facility at its main plant. The $12 million investment is expected to increase output by 35%, meeting growing domestic and export demand. CEO Sarah Goldberg said the company remains committed to the highest food safety standards, with the new facility incorporating state-of-the-art quality control systems.\n\nThe expansion comes as the canned fish market sees a resurgence in consumer interest, driven by health trends favoring high-protein, shelf-stable foods. HappyTuna reported revenues of $250 million last year, with exports to 14 countries.",
                "author": "News Desk",
                "category": "update",
                "tags": '["HappyTuna","production","expansion"]',
                "published_at": "2024-06-03T09:00:00+00:00",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "views": 142,
                "source_urls": "[]",
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Food safety regulators tighten inspection rules for canned goods manufacturers",
                "body": "The Ministry of Health announced new mandatory monthly inspection protocols for all canned food manufacturers operating in the country. The revised guidelines, effective from July 2024, require companies to submit detailed production batch reports and maintain real-time contamination monitoring logs accessible to health inspectors.\n\nThe move follows a series of recalls in the European market linked to listeria and salmonella contamination in canned seafood products. 'We are taking a proactive stance,' said the Ministry spokesperson. 'Consumers deserve full confidence in packaged food safety.'\n\nIndustry groups have broadly welcomed the new rules while calling for a transition period to allow manufacturers to update their systems.",
                "author": "Regulatory Affairs Reporter",
                "category": "investigative",
                "tags": '["food safety","regulation","recall","salmonella"]',
                "published_at": "2024-06-07T11:30:00+00:00",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "views": 389,
                "source_urls": "[]",
            },
            {
                "id": str(uuid.uuid4()),
                "title": "What really happens during a food recall — a step-by-step guide",
                "body": "Food recalls are more common than most people realise. In 2023 alone, over 800 food products were recalled across Europe and North America. But what actually happens when a company discovers a problem?\n\nStep one is containment: halting production and identifying which batches are affected. This sounds straightforward, but tracing contamination in a large facility can take days. Step two is regulatory notification — companies are legally required to inform health authorities within 24 to 48 hours of confirming a safety risk.\n\nStep three is the public announcement. Companies face a difficult calculation: how much to disclose, and when. Too early, and panic sets in before facts are known. Too late, and regulators — and the press — lose patience.\n\nFor consumers, the message is simple: check the batch numbers posted on company websites and return affected products immediately.",
                "author": "Consumer Affairs Editor",
                "category": "investigative",
                "tags": '["recall","food safety","consumer","health"]',
                "published_at": "2024-06-08T14:00:00+00:00",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "views": 712,
                "source_urls": "[]",
            },
        ]
        for a in seed_articles:
            conn.execute(
                "INSERT INTO articles VALUES (:id,:title,:body,:author,:category,:tags,:published_at,:created_at,:views,:source_urls)",
                a,
            )
        conn.commit()
    conn.close()


init_db()


# --- Helpers ---
def get_sim_time() -> str:
    try:
        r = httpx.get(f"{NTP_URL}/time", timeout=3)
        return r.json()["sim_time"]
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def row_to_dict(row) -> dict:
    import json
    d = dict(row)
    for field in ("tags", "source_urls"):
        try:
            d[field] = json.loads(d[field])
        except Exception:
            d[field] = []
    return d


# --- Models ---
class ArticleCreate(BaseModel):
    title: str
    body: str
    author: str
    category: str = "update"
    tags: List[str] = []
    source_urls: List[str] = []


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "service": "news-website"}


@app.get("/feed")
def get_feed(limit: int = Query(20, le=100)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, author, category, tags, published_at FROM articles ORDER BY published_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    import json
    return [
        {**dict(r), "tags": json.loads(r["tags"])}
        for r in rows
    ]


@app.get("/articles")
def list_articles(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = Query(20, le=100),
):
    conn = get_db()
    query = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if tag:
        query += " AND tags LIKE ?"
        params.append(f'%"{tag}"%')
    query += " ORDER BY published_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/articles/search")
def search_articles(q: str = Query(..., min_length=1), limit: int = 10):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE title LIKE ? OR body LIKE ? ORDER BY published_at DESC LIMIT ?",
        (f"%{q}%", f"%{q}%", limit),
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/articles/{article_id}")
def get_article(article_id: str):
    conn = get_db()
    conn.execute("UPDATE articles SET views = views + 1 WHERE id = ?", (article_id,))
    conn.commit()
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return row_to_dict(row)


@app.post("/articles", status_code=201)
def publish_article(article: ArticleCreate):
    import json
    article_id = str(uuid.uuid4())
    sim_time = get_sim_time()
    real_time = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    conn.execute(
        "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            article_id,
            article.title,
            article.body,
            article.author,
            article.category,
            json.dumps(article.tags),
            sim_time,
            real_time,
            0,
            json.dumps(article.source_urls),
        ),
    )
    conn.commit()
    conn.close()
    return {
        "id": article_id,
        "title": article.title,
        "published_at": sim_time,
        "message": "Article published successfully",
    }


# --- NTP proxy (so the browser UI can call NTP without CORS issues) ---
@app.get("/time-proxy")
def time_proxy():
    try:
        r = httpx.get(f"{NTP_URL}/time", timeout=3)
        return r.json()
    except Exception:
        return {"sim_time": datetime.now(timezone.utc).isoformat(), "sim_time_human": "NTP unavailable", "real_time": datetime.now(timezone.utc).isoformat(), "speed_multiplier": "?"}


# --- Web UI ---
@app.get("/", response_class=HTMLResponse)
def web_ui():
    return HTMLResponse(content=open("/app/ui.html").read())

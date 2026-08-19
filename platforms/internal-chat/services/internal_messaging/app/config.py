"""Configuration — env only (KB: config in one place).

Kept to stdlib `os.environ` so the service has no settings-framework dependency.
Every backend is chosen here; defaults are the zero-infra path (SQLite, no cache,
no bus) so tests and local dev need nothing running.

Storage (durable state):
- CHAT_STORE   : "sqlite" (default) | "postgres"
- CHAT_DB_PATH : SQLite location (when CHAT_STORE=sqlite)
- CHAT_DB_URL  : Postgres DSN (when CHAT_STORE=postgres), e.g. postgresql://u:p@host/db

Active state:
- CHAT_CACHE     : "none" (default) | "redis"
- CHAT_REDIS_URL : Redis url (cache and/or CHAT_BUS=redis)

Events:
- CHAT_BUS           : "none" (default) | "kafka" | "redis"
- CHAT_KAFKA_BROKERS : bootstrap servers when CHAT_BUS=kafka (e.g. kafka:9092)
- CHAT_KAFKA_TOPIC   : topic (default chat.message_posted)

Other:
- CHAT_PORT : REST/MCP port
- NTP_URL   : world time service. Unset → WallClock (local dev)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "chat.db"


@dataclass(frozen=True)
class Settings:
    # storage
    store: str = os.environ.get("CHAT_STORE", "sqlite")
    db_path: str = os.environ.get("CHAT_DB_PATH", str(_DEFAULT_DB))
    db_url: str = os.environ.get("CHAT_DB_URL", "postgresql://bitrix:bitrix@localhost/bitrix_chat")
    # active state
    cache: str = os.environ.get("CHAT_CACHE", "none")
    redis_url: str = os.environ.get("CHAT_REDIS_URL", "redis://localhost:6379/0")
    # events
    bus: str = os.environ.get("CHAT_BUS", "none")
    kafka_brokers: str = os.environ.get("CHAT_KAFKA_BROKERS", "localhost:9092")
    kafka_topic: str = os.environ.get("CHAT_KAFKA_TOPIC", "chat.message_posted")
    # other
    port: int = int(os.environ.get("CHAT_PORT", "8080"))
    ntp_url: str | None = os.environ.get("NTP_URL") or None


def load_settings() -> Settings:
    return Settings()

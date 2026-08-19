"""App factory — wires the store, cache, registry, events, and transports together.

Every backend is selected from `Settings` (env). Zero-infra defaults: SQLite store,
no cache, `NullPublisher` — so tests and local dev need nothing running. Production
(compose) sets `CHAT_STORE=postgres`, `CHAT_CACHE=redis`, `CHAT_BUS=kafka`. Swap to
`FixedClock` + `SeededIdFactory` (via `build_service`) for a replayable run.

`create_app()` returns the REST FastAPI app (run with uvicorn). `build_service`
and `transport.mcp.tools.build_chat_client` give the in-process MCP door for
`mcp_core` agents.
"""
from __future__ import annotations

from fastapi import FastAPI

from services.internal_messaging.app.config import Settings, load_settings
from services.internal_messaging.domain.service import InternalMessagingService
from services.internal_messaging.domain.store import SqliteStore
from services.internal_messaging.domain.store_base import StoreProtocol
from services.internal_messaging.integration.cache import Cache, NullCache, RedisCache
from services.internal_messaging.integration.clock import (
    Clock,
    NtpClock,
    WallClock,
    http_time_fetcher,
)
from services.internal_messaging.integration.events import (
    BusPublisher,
    KafkaPublisher,
    NullPublisher,
    Publisher,
    RedisStreamsBus,
)
from services.internal_messaging.integration.ids import IdFactory, UuidFactory
from services.internal_messaging.integration.identity import Registry, default_registry


def build_clock(settings: Settings) -> Clock:
    if settings.ntp_url:
        return NtpClock(http_time_fetcher(settings.ntp_url))
    return WallClock()


def build_store(settings: Settings, clock: Clock, ids: IdFactory) -> StoreProtocol:
    if settings.store == "postgres":
        from services.internal_messaging.domain.store_postgres import PostgresStore

        return PostgresStore(settings.db_url, clock, ids)
    return SqliteStore(settings.db_path, clock, ids)


def build_cache(settings: Settings) -> Cache:
    if settings.cache == "redis":
        return RedisCache(settings.redis_url)
    return NullCache()


def build_publisher(settings: Settings) -> Publisher:
    if settings.bus == "kafka":
        return KafkaPublisher(settings.kafka_brokers, settings.kafka_topic)
    if settings.bus == "redis":
        return BusPublisher(RedisStreamsBus(settings.redis_url))
    return NullPublisher()


def build_service(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    ids: IdFactory | None = None,
    registry: Registry | None = None,
    publisher: Publisher | None = None,
    cache: Cache | None = None,
) -> InternalMessagingService:
    settings = settings or load_settings()
    store = build_store(settings, clock or build_clock(settings), ids or UuidFactory())
    return InternalMessagingService(
        store,
        registry or default_registry(),
        publisher or build_publisher(settings),
        cache or build_cache(settings),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    return create_rest_app_for(build_service(settings))


def create_rest_app_for(service: InternalMessagingService) -> FastAPI:
    # local import keeps FastAPI out of the import path for pure-domain/MCP use
    from services.internal_messaging.transport.rest.app import create_rest_app

    return create_rest_app(service)


app = create_app()

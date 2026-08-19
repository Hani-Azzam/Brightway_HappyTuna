"""Database plumbing shared by every service that touches Postgres.

Three small factories:
  - `Base`                  the declarative base every ORM model inherits from.
  - `make_engine(url)`      one connection pool to Postgres.
  - `make_session_factory`  a factory that hands out short-lived Sessions.

A `Session` is a unit of work: you open one per request, do reads/writes inside
it, commit, and close. The engine (the pool) is created once at startup.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """All tables (Channel, Membership, Message, OutboxEvent) subclass this.

    SQLAlchemy collects their definitions on `Base.metadata`, which Alembic and
    the test fixtures use to create/drop the schema.
    """


def make_engine(url: str):
    # pool_pre_ping checks a connection is alive before handing it out, so a
    # dropped Postgres connection surfaces as a clean retry instead of a crash.
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine) -> sessionmaker[Session]:
    # autoflush/autocommit off → we control exactly when SQL is sent and when a
    # transaction commits. The service layer calls commit() deliberately.
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)

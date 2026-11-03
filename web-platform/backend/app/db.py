"""Database engine and session management (SQLAlchemy 2.x).

PostgreSQL is the production target. SQLite is accepted for unit tests and
quick local experiments; all models use portable column types.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def configure_engine(url: str | None = None) -> Engine:
    """(Re)create the global engine. Called at startup and by the test suite."""
    global _engine, _SessionFactory
    url = url or get_settings().database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(pool_size=10, max_overflow=10)
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce ON DELETE CASCADE in SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    _SessionFactory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine if _engine is not None else configure_engine()


def session_factory() -> sessionmaker[Session]:
    if _SessionFactory is None:
        configure_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db(retries: int = 30, delay_s: float = 2.0) -> None:
    """Create tables. Waits for the database to accept connections (containers start in
    parallel) and, on PostgreSQL, serialises schema creation across workers/replicas
    with an advisory lock."""
    import logging
    import time

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from . import models  # noqa: F401  (register tables)

    engine = get_engine()
    for attempt in range(1, retries + 1):
        try:
            with engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_xact_lock(724001)"))
                Base.metadata.create_all(conn)
            return
        except OperationalError as exc:
            if attempt == retries:
                raise
            logging.getLogger(__name__).warning("Database not ready (%s/%s): %s", attempt, retries, exc.__class__.__name__)
            time.sleep(delay_s)

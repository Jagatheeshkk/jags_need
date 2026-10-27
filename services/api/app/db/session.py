from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(url: str, pool_size: int = 3) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
            # Let SQLAlchemy own transactions so SAVEPOINTs (begin_nested) work on pysqlite.
            dbapi_conn.isolation_level = None

        @event.listens_for(engine, "begin")
        def _on_begin(conn):
            conn.exec_driver_sql("BEGIN")

        return engine
    # Small pool + pre-ping: free Postgres tiers cap connections and suspend idle compute,
    # so stale connections after a suspend must be detected and replaced.
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=300,
        # prepare_threshold=None: no server-side prepared statements, so pooled endpoints
        # (PgBouncer transaction mode, e.g. Neon's "-pooler" host) work reliably.
        connect_args={"connect_timeout": 15, "prepare_threshold": None},
    )


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    return build_engine(s.database_url, s.db_pool_size)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()

"""Test fixtures.

By default tests run against a throwaway SQLite file built with the real Alembic migrations.
Set TEST_DATABASE_URL to a disposable PostgreSQL database to run the same suite on Postgres
(all tables in it are dropped and recreated).
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP_DB = Path(__file__).parent / ".test.db"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_TMP_DB.as_posix()}"

os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=TEST_DB_URL,
    SECRET_KEY="test-secret-key-0123456789-abcdefghijklmnop",
    LOGIN_MAX_ATTEMPTS="3",
    LOGIN_WINDOW_SECONDS="60",
    AI_PROVIDER="rule_based",
)
os.environ.pop("BOOTSTRAP_TOKEN", None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.api import deps  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import build_engine, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402

API_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "correct horse battery staple"
EMAIL = "owner@example.com"


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.attributes["database_url"] = get_settings().model_validate({"database_url": url}).database_url
    cfg.attributes["configure_logger"] = False
    return cfg


def _reset_schema(engine: Engine) -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    else:
        _TMP_DB.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = get_settings().database_url
    eng = build_engine(url)
    _reset_schema(eng)
    command.upgrade(alembic_config(url), "head")
    yield eng
    eng.dispose()
    if eng.dialect.name == "sqlite":
        _TMP_DB.unlink(missing_ok=True)


@pytest.fixture
def db_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client(db_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    deps.get_login_limiter.cache_clear()
    get_settings.cache_clear()
    app = create_app()

    def _db() -> Iterator[Session]:
        s = db_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        token = c.get("/api/auth/csrf").json()["csrf_token"]
        c.headers["x-csrf-token"] = token
        yield c


@pytest.fixture
def owner(client: TestClient) -> TestClient:
    """Client logged in as the owner."""
    r = client.post("/api/auth/setup", json={"email": EMAIL, "password": PASSWORD, "display_name": "Test Owner"})
    assert r.status_code == 201, r.text
    return client

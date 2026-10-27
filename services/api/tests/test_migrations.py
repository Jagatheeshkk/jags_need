from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.models import Base

EXPECTED_TABLES = {
    "users",
    "candidate_profiles",
    "employment_history",
    "skills",
    "candidate_skills",
    "portals",
    "portal_connections",
    "jobs",
    "job_sources",
    "job_matches",
    "resumes",
    "applications",
    "application_events",
    "automation_rules",
    "profile_sync_runs",
    "approval_requests",
    "notifications",
    "audit_logs",
}


def test_all_required_tables_exist(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES


def test_migrations_match_models(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_duplicate_application_constraint(engine: Engine) -> None:
    uniques = inspect(engine).get_unique_constraints("applications")
    assert any(set(u["column_names"]) == {"user_id", "job_id"} for u in uniques)


def test_downgrade_and_upgrade_roundtrip(tmp_path) -> None:
    from tests.conftest import alembic_config

    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

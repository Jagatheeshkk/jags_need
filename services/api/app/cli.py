"""Maintenance commands.

python -m app.cli migrate            # alembic upgrade head
python -m app.cli seed               # portal rows (idempotent)
python -m app.cli seed-sample-jobs   # synthetic jobs from the mock connector (idempotent)
python -m app.cli ingest             # refresh jobs + scores for the owner (scheduled task)
python -m app.cli readiness          # print the deployment readiness report
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.connectors.base import JobFilters
from app.connectors.mock import MockConnector
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import User
from app.services import ingestion, portal_service, readiness

API_ROOT = Path(__file__).resolve().parent.parent


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def seed() -> None:
    with get_sessionmaker()() as db:
        portals = portal_service.ensure_portals(db)
        print(f"portals: {', '.join(sorted(portals))}")


def seed_sample_jobs() -> None:
    with get_sessionmaker()() as db:
        portal = portal_service.ensure_portals(db)["mock"]
        stats = ingestion.IngestStats()
        ingestion.ingest_from(db, portal, MockConnector(), JobFilters(limit=100), stats, datetime.now(UTC))
        print(f"synthetic jobs: {stats.created} created, {stats.updated} updated, {stats.merged} merged as duplicates")


def ingest() -> int:
    """Refresh jobs for the owner account (for a local scheduled task)."""
    with get_sessionmaker()() as db:
        user = db.scalars(select(User)).first()
        if user is None:
            print("No owner account yet")
            return 1
        run = ingestion.run_refresh(db, user, trigger="scheduled")
        print(json.dumps({"status": run.status, "result": run.result, "error": run.error}, indent=2, default=str))
        return 0 if run.status == "succeeded" else 1


def show_readiness() -> int:
    with get_sessionmaker()() as db:
        report = readiness.run(db, get_settings())
    print(json.dumps(report.model_dump(), indent=2))
    return 0 if report.ready else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument("command", choices=["migrate", "seed", "seed-sample-jobs", "ingest", "readiness"])
    args = parser.parse_args(argv)
    if args.command == "migrate":
        migrate()
    elif args.command == "seed":
        seed()
    elif args.command == "seed-sample-jobs":
        seed_sample_jobs()
    elif args.command == "ingest":
        return ingest()
    else:
        return show_readiness()
    return 0


if __name__ == "__main__":
    sys.exit(main())

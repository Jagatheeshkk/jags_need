"""Maintenance commands.

python -m app.cli migrate            # alembic upgrade head
python -m app.cli seed               # portal rows (idempotent)
python -m app.cli seed-sample-jobs   # synthetic jobs from the mock connector (idempotent)
python -m app.cli readiness          # print the deployment readiness report
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.connectors.base import JobFilters
from app.connectors.mock import MockConnector
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Job, JobSource
from app.services import portal_service, readiness

API_ROOT = Path(__file__).resolve().parent.parent


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def content_hash(title: str, company: str, location: str | None, description: str | None) -> str:
    norm = "|".join(" ".join((x or "").lower().split()) for x in (title, company, location, description))
    return hashlib.sha256(norm.encode()).hexdigest()


def seed() -> None:
    with get_sessionmaker()() as db:
        portals = portal_service.ensure_portals(db)
        print(f"portals: {', '.join(sorted(portals))}")


def seed_sample_jobs() -> None:
    with get_sessionmaker()() as db:
        portal = portal_service.ensure_portals(db)["mock"]
        created = 0
        for pj in MockConnector().search_jobs(JobFilters(limit=100)):
            exists = db.scalars(
                select(JobSource).where(JobSource.portal_id == portal.id, JobSource.external_id == pj.external_id)
            ).first()
            if exists:
                continue
            job = Job(
                title=pj.title,
                company=pj.company,
                location=pj.location,
                work_arrangement=pj.work_arrangement,
                description=pj.description,
                salary_min=pj.salary_min,
                salary_max=pj.salary_max,
                salary_currency=pj.salary_currency,
                experience_min=pj.experience_min,
                experience_max=pj.experience_max,
                canonical_url=pj.url,
                posted_at=pj.posted_at,
                is_synthetic=True,
                content_hash=content_hash(pj.title, pj.company, pj.location, pj.description),
            )
            db.add(job)
            db.flush()
            db.add(
                JobSource(
                    job_id=job.id,
                    portal_id=portal.id,
                    external_id=pj.external_id,
                    source_url=pj.url,
                    raw_payload=pj.model_dump(mode="json"),
                )
            )
            created += 1
        db.commit()
        print(f"synthetic jobs created: {created}")


def show_readiness() -> int:
    with get_sessionmaker()() as db:
        report = readiness.run(db, get_settings())
    print(json.dumps(report.model_dump(), indent=2))
    return 0 if report.ready else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    parser.add_argument("command", choices=["migrate", "seed", "seed-sample-jobs", "readiness"])
    args = parser.parse_args(argv)
    if args.command == "migrate":
        migrate()
    elif args.command == "seed":
        seed()
    elif args.command == "seed-sample-jobs":
        seed_sample_jobs()
    else:
        return show_readiness()
    return 0


if __name__ == "__main__":
    sys.exit(main())

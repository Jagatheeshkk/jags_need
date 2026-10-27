"""Collect jobs from connectors that are permitted to search, normalise and de-duplicate them.

Duplicate detection, in order:
  1. same portal + external id      -> same listing seen again (update)
  2. same canonical URL             -> same listing from another feed (merge as a new source)
  3. same normalised company and near-identical title + description -> repost (merge)
"""

import contextlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorNotSupported, JobFilters, PortalConnector, PortalJob
from app.connectors.registry import all_connectors
from app.models import Job, JobSource, Notification, Portal, TaskRun, User
from app.services import automation, match_service, portal_service, profile_service, tasks
from app.services.normalize import (
    MAX_DESCRIPTION,
    MAX_TITLE,
    as_utc,
    canonical_url,
    clean_text,
    company_key,
    content_hash,
    jaccard,
    shingles,
    tokens,
)

TITLE_SIMILARITY = 0.8
DESCRIPTION_SIMILARITY = 0.6
KIND = "job_refresh"

Outcome = Literal["created", "updated", "merged"]


@dataclass
class IngestStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    merged: int = 0
    expired: int = 0
    scored: int = 0
    portals_searched: list[str] = field(default_factory=list)
    portals_skipped: dict[str, str] = field(default_factory=dict)
    portal_errors: dict[str, str] = field(default_factory=dict)


def filters_for(db: Session, user: User) -> JobFilters:
    profile = profile_service.get_or_create(db, user)
    locations = list(profile.preferred_locations)
    if profile.work_arrangement in {"remote", "any"} and "remote" not in {x.lower() for x in locations}:
        locations.append("Remote")
    return JobFilters(
        titles=profile.preferred_roles[:20],
        keywords=profile.search_keywords[:20],
        locations=locations[:20] if profile.preferred_locations else [],
        limit=100,
    )


def _apply(job: Job, pj: PortalJob, now: datetime) -> None:
    job.title = clean_text(pj.title, MAX_TITLE) or "Untitled"
    job.company = clean_text(pj.company, 200) or "Unknown company"
    job.company_key = company_key(job.company)
    job.location = clean_text(pj.location, 200)
    job.work_arrangement = pj.work_arrangement if pj.work_arrangement in {"remote", "hybrid", "onsite"} else None
    job.description = clean_text(pj.description, MAX_DESCRIPTION)
    job.skills = [s for s in (clean_text(x, 100) for x in pj.skills[:50]) if s]
    job.salary_min, job.salary_max = pj.salary_min, pj.salary_max
    job.salary_currency = pj.salary_currency
    job.experience_min, job.experience_max = pj.experience_min, pj.experience_max
    job.posted_at, job.expires_at = pj.posted_at, pj.expires_at
    job.is_synthetic = pj.is_synthetic
    job.content_hash = content_hash(job.title, job.company, job.location, job.description)
    job.last_seen_at = now
    if job.status == "expired" and (pj.expires_at is None or pj.expires_at > now):
        job.status = "active"


def find_duplicate(db: Session, pj: PortalJob) -> Job | None:
    url = canonical_url(pj.url)
    if url:
        job = db.scalars(select(Job).where(Job.canonical_url == url)).first()
        if job:
            return job
    title = clean_text(pj.title, MAX_TITLE) or ""
    description = clean_text(pj.description, MAX_DESCRIPTION)
    chash = content_hash(title, clean_text(pj.company, 200) or "", clean_text(pj.location, 200), description)
    key = company_key(pj.company)
    if not key:
        return None
    for job in db.scalars(select(Job).where(Job.company_key == key)):
        if job.content_hash == chash:
            return job
        if (
            jaccard(tokens(job.title), tokens(title)) >= TITLE_SIMILARITY
            and jaccard(shingles(job.description), shingles(description)) >= DESCRIPTION_SIMILARITY
        ):
            return job
    return None


def upsert(db: Session, portal: Portal, pj: PortalJob, now: datetime) -> Outcome:
    src = db.scalars(
        select(JobSource).where(JobSource.portal_id == portal.id, JobSource.external_id == pj.external_id)
    ).first()
    payload = pj.model_dump(mode="json")
    if src is not None:
        job = db.get(Job, src.job_id)
        assert job is not None
        _apply(job, pj, now)
        src.raw_payload, src.fetched_at, src.source_url = payload, now, pj.url
        return "updated"

    dup = find_duplicate(db, pj)
    if dup is not None:
        dup.last_seen_at = now
        if pj.posted_at and (dup.posted_at is None or pj.posted_at < as_utc(dup.posted_at)):
            dup.posted_at = pj.posted_at  # keep the earliest sighting
        db.add(
            JobSource(
                job_id=dup.id,
                portal_id=portal.id,
                external_id=pj.external_id,
                source_url=pj.url,
                raw_payload=payload,
                fetched_at=now,
            )
        )
        return "merged"

    job = Job(canonical_url=canonical_url(pj.url))
    _apply(job, pj, now)
    db.add(job)
    db.flush()
    db.add(
        JobSource(
            job_id=job.id,
            portal_id=portal.id,
            external_id=pj.external_id,
            source_url=pj.url,
            raw_payload=payload,
            fetched_at=now,
        )
    )
    return "created"


def ingest_from(
    db: Session, portal: Portal, connector: PortalConnector, filters: JobFilters, stats: IngestStats, now: datetime
) -> None:
    try:
        found = connector.search_jobs(filters)
    except ConnectorNotSupported as exc:
        stats.portals_skipped[connector.code] = str(exc)
        return
    stats.portals_searched.append(connector.code)
    stats.fetched += len(found)
    for pj in found:
        with db.begin_nested():  # one bad record does not abort the whole refresh
            outcome = upsert(db, portal, pj, now)
        setattr(stats, outcome, getattr(stats, outcome) + 1)
    db.commit()


def mark_expired(db: Session, now: datetime) -> int:
    result = db.execute(
        update(Job)
        .where(Job.status == "active", Job.expires_at.is_not(None), Job.expires_at <= now)
        .values(status="expired")
    )
    return int(getattr(result, "rowcount", 0) or 0)


def run_refresh(
    db: Session,
    user: User,
    trigger: str = "manual",
    connectors: list[PortalConnector] | None = None,
    filters: JobFilters | None = None,
) -> TaskRun:
    run = tasks.start(db, user.id, KIND, trigger)
    if run.status != "running":  # idempotent replay of a finished run
        return run
    stats = IngestStats()
    now = datetime.now(UTC)
    try:
        portals = portal_service.ensure_portals(db)
        filters = filters or filters_for(db, user)
        for connector in connectors or all_connectors():
            if not connector.get_capabilities().search_jobs:
                stats.portals_skipped[connector.code] = "search not permitted / not verified"
                continue
            try:
                ingest_from(db, portals[connector.code], connector, filters, stats, now)
            except Exception as exc:  # noqa: BLE001 - one failing portal must not stop the others
                db.rollback()
                stats.portal_errors[connector.code] = f"{type(exc).__name__}: {str(exc)[:200]}"
            tasks.heartbeat(db, run)
        stats.expired = mark_expired(db, now)
        db.commit()
        stats.scored = match_service.rescore_all(db, user)
        if stats.created:
            db.add(
                Notification(
                    user_id=user.id,
                    kind="jobs",
                    title=f"{stats.created} new job(s) found",
                    body="Open Job Discovery to review scores and explanations.",
                    link="/jobs",
                    dedupe_key=f"job_refresh:{run.id}",
                )
            )
        finished = tasks.finish(db, run, asdict(stats))
    except Exception as exc:
        return tasks.fail(db, run, f"{type(exc).__name__}: {exc}", asdict(stats))
    rules = automation.get_rules(db, user)
    if rules.enabled and not rules.global_pause:
        # Separate task run: an automation problem never marks the refresh as failed.
        with contextlib.suppress(tasks.TaskAlreadyRunning):
            automation.run(db, user, trigger="after_refresh")
    return finished


def refresh_due(db: Session, user: User, now: datetime | None = None) -> bool:
    profile = profile_service.get_or_create(db, user)
    last = tasks.latest(db, user.id, KIND, status="succeeded")
    if last is None or last.finished_at is None:
        return True
    finished = last.finished_at if last.finished_at.tzinfo else last.finished_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - finished >= timedelta(hours=profile.refresh_interval_hours)

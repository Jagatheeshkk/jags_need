import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Job, JobMatch, JobSource, Portal, TaskRun
from app.schemas.jobs import (
    FeedbackIn,
    JobDetail,
    JobList,
    JobSourceOut,
    JobSummary,
    ManualJobIn,
    ManualJobOut,
    MatchOut,
    SavedIn,
    TaskRunOut,
)
from app.services import audit, ingestion, match_service, tasks
from app.services.normalize import freshness

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _match_out(m: JobMatch | None) -> MatchOut | None:
    if m is None:
        return None
    return MatchOut(
        score=float(m.score),
        matched_skills=m.matched_skills,
        missing_skills=m.missing_skills,
        eligibility=m.eligibility,
        components=m.breakdown.get("components", {}),
        engine=m.engine,
        is_saved=m.is_saved,
        feedback=m.feedback,
    )


def _summary(job: Job, m: JobMatch | None, source_count: int) -> dict:
    return dict(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        work_arrangement=job.work_arrangement,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        experience_min=job.experience_min,
        experience_max=job.experience_max,
        posted_at=job.posted_at,
        expires_at=job.expires_at,
        last_seen_at=job.last_seen_at,
        status=job.status,
        freshness=freshness(job.posted_at, job.expires_at, job.status),
        is_synthetic=job.is_synthetic,
        source_count=source_count,
        match=_match_out(m),
    )


def _load(db: DbSession, user: CurrentUser) -> list[tuple[Job, JobMatch | None, int]]:
    match_service.rescore_all(db, user)  # cheap when nothing changed; keeps scores in step with the profile
    matches = {m.job_id: m for m in db.scalars(select(JobMatch).where(JobMatch.user_id == user.id))}
    counts: dict[uuid.UUID, int] = {}
    for jid in db.scalars(select(JobSource.job_id)):
        counts[jid] = counts.get(jid, 0) + 1
    return [(j, matches.get(j.id), counts.get(j.id, 0)) for j in db.scalars(select(Job))]


@router.get("", response_model=JobList)
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    role: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    work_arrangement: Literal["remote", "hybrid", "onsite"] | None = None,
    min_score: float = Query(default=0, ge=0, le=100),
    min_salary: int | None = Query(default=None, ge=0),
    saved_only: bool = False,
    eligible_only: bool = False,
    include_expired: bool = False,
    include_synthetic: bool = True,
    sort: Literal["score", "newest"] = "score",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobList:
    rows = _load(db, user)

    def keep(job: Job, m: JobMatch | None) -> bool:
        if not include_expired and freshness(job.posted_at, job.expires_at, job.status) == "expired":
            return False
        if not include_synthetic and job.is_synthetic:
            return False
        if q and q.lower() not in f"{job.title} {job.company} {job.description or ''}".lower():
            return False
        if role and role.lower() not in job.title.lower():
            return False
        if location:
            want = location.lower()
            if not (want in (job.location or "").lower() or (want == "remote" and job.work_arrangement == "remote")):
                return False
        if work_arrangement and job.work_arrangement != work_arrangement:
            return False
        top = job.salary_max or job.salary_min
        if min_salary is not None and top is not None and top < min_salary:  # unknown salary is kept
            return False
        if min_score and (m is None or float(m.score) < min_score):
            return False
        if saved_only and not (m and m.is_saved):
            return False
        return not (eligible_only and (m is None or m.eligibility.get("status") != "eligible"))

    kept = [r for r in rows if keep(r[0], r[1])]
    epoch = datetime.min.replace(tzinfo=UTC)
    if sort == "newest":
        kept.sort(key=lambda r: r[0].posted_at.replace(tzinfo=UTC) if r[0].posted_at else epoch, reverse=True)
    else:
        kept.sort(key=lambda r: float(r[1].score) if r[1] else -1, reverse=True)
    last = tasks.latest(db, user.id, ingestion.KIND)
    return JobList(
        items=[JobSummary(**_summary(*r)) for r in kept[offset : offset + limit]],
        total=len(kept),
        last_refresh=TaskRunOut.model_validate(last) if last else None,
        refresh_due=ingestion.refresh_due(db, user),
    )


@router.post("/refresh", response_model=TaskRunOut)
def refresh(user: CurrentUser, db: DbSession, only_if_due: bool = False) -> TaskRun:
    """Search every permitted connector now. With only_if_due, does nothing until the interval passes."""
    if only_if_due and not ingestion.refresh_due(db, user):
        last = tasks.latest(db, user.id, ingestion.KIND, status="succeeded")
        assert last is not None
        return last
    try:
        return ingestion.run_refresh(db, user, trigger="scheduled" if only_if_due else "manual")
    except tasks.TaskAlreadyRunning as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A refresh is already running") from exc


@router.post("/manual", response_model=ManualJobOut, status_code=status.HTTP_201_CREATED)
def add_manual_job(
    body: ManualJobIn, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> ManualJobOut:
    """Add a real listing you found on a manual-only portal (the server never visits the link)."""
    fields = body.model_dump(exclude={"portal"})
    try:
        job, outcome = ingestion.capture_manual(db, user, body.portal, fields)
    except ingestion.CaptureRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    audit.record(
        db,
        "job.captured_manually",
        user_id=user.id,
        entity_type="job",
        entity_id=job.id,
        details={"portal": body.portal, "outcome": outcome},
        request=request,
    )
    db.commit()
    if outcome != "created":
        response.status_code = status.HTTP_200_OK
    return ManualJobOut(job_id=job.id, outcome=outcome)


@router.post("/rescore")
def rescore(user: CurrentUser, db: DbSession) -> dict[str, int]:
    return {"scored": match_service.rescore_all(db, user, force=True)}


@router.get("/runs", response_model=list[TaskRunOut])
def runs(user: CurrentUser, db: DbSession, limit: int = Query(default=10, ge=1, le=50)) -> list[TaskRun]:
    tasks.recover_stale(db)
    stmt = select(TaskRun).where(TaskRun.user_id == user.id).order_by(TaskRun.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/digest")
def digest(user: CurrentUser, db: DbSession, days: int = Query(default=1, ge=1, le=14)) -> Response:
    """Markdown digest of jobs seen in the last `days` days, best matches first."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = [
        (j, m)
        for j, m, _ in _load(db, user)
        if j.last_seen_at
        and j.last_seen_at.replace(tzinfo=UTC) >= since
        and freshness(j.posted_at, j.expires_at, j.status) != "expired"
    ]
    rows.sort(key=lambda r: float(r[1].score) if r[1] else -1, reverse=True)
    today = datetime.now(UTC).date().isoformat()
    lines = [f"# Job digest - {today}", "", f"{len(rows)} job(s) seen in the last {days} day(s).", ""]
    if any(j.is_synthetic for j, _ in rows):
        lines += ["> Entries marked SYNTHETIC come from the mock connector and are not real openings.", ""]
    for j, m in rows:
        tag = " [SYNTHETIC]" if j.is_synthetic else ""
        score = f"{float(m.score):g}/100" if m else "not scored"
        elig = m.eligibility.get("status", "unknown") if m else "unknown"
        lines += [
            f"## {j.title} - {j.company}{tag}",
            f"- Match: {score} (eligibility: {elig})",
            f"- Where: {j.location or 'not stated'} ({j.work_arrangement or 'arrangement not stated'})",
        ]
        if m and m.missing_skills:
            lines.append(f"- Missing skills: {', '.join(m.missing_skills)}")
        lines.append("")
    return Response(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="job-digest-{today}.md"'},
    )


def _get(db: DbSession, user: CurrentUser, job_id: uuid.UUID) -> tuple[Job, JobMatch]:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    match_service.rescore_all(db, user)
    m = db.scalars(select(JobMatch).where(JobMatch.user_id == user.id, JobMatch.job_id == job_id)).first()
    assert m is not None
    return job, m


@router.get("/{job_id}", response_model=JobDetail)
def job_detail(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobDetail:
    job, m = _get(db, user, job_id)
    srcs = db.execute(
        select(JobSource, Portal.code)
        .join(Portal, Portal.id == JobSource.portal_id)
        .where(JobSource.job_id == job.id)
        .order_by(JobSource.fetched_at)
    ).all()
    return JobDetail(
        **_summary(job, m, len(srcs)),
        description=job.description,
        skills=job.skills,
        canonical_url=job.canonical_url,
        sources=[
            JobSourceOut(portal=code, external_id=s.external_id, url=s.source_url, fetched_at=s.fetched_at)
            for s, code in srcs
        ],
        explanation=m.explanation,
    )


@router.put("/{job_id}/saved", response_model=MatchOut)
def set_saved(job_id: uuid.UUID, body: SavedIn, request: Request, user: CurrentUser, db: DbSession) -> MatchOut:
    _, m = _get(db, user, job_id)
    m.is_saved = body.saved
    audit.record(
        db,
        "job.saved" if body.saved else "job.unsaved",
        user_id=user.id,
        entity_type="job",
        entity_id=job_id,
        request=request,
    )
    db.commit()
    out = _match_out(m)
    assert out is not None
    return out


@router.put("/{job_id}/feedback", response_model=MatchOut)
def set_feedback(job_id: uuid.UUID, body: FeedbackIn, request: Request, user: CurrentUser, db: DbSession) -> MatchOut:
    _, m = _get(db, user, job_id)
    m.feedback = body.feedback
    audit.record(
        db,
        "job.feedback",
        user_id=user.id,
        entity_type="job",
        entity_id=job_id,
        details={"feedback": body.feedback},
        request=request,
    )
    db.commit()
    out = _match_out(m)
    assert out is not None
    return out

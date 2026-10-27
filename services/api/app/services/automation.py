"""Automation rules engine and approval workflow.

For each candidate job the engine runs an ordered list of checks and decides:

  skip      - a rule excludes the job (score, title, location, company, salary, eligibility...)
  approval  - allowed in principle, but something needs a human: the portal does not permit
              automated submission, auto-apply is off for the portal, eligibility or salary is
              unknown, or a screening answer needs confirmation (salary commitment, legal
              declaration, sensitive attestation, unknown answer)
  submit    - every check passed with no doubt

Submission happens only through a connector whose capabilities allow it. Today that is only the
mock connector, so every automated submission is simulated and flagged as such.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.registry import get_connector
from app.models import (
    Application,
    ApprovalRequest,
    AutomationRule,
    CandidateProfile,
    Job,
    JobMatch,
    JobSource,
    Notification,
    Portal,
    Resume,
    TaskRun,
    User,
)
from app.services import applications, documents, match_service, profile_service, tasks
from app.services.normalize import company_key, freshness

KIND = "automation"
APPROVAL_TTL = timedelta(days=7)

Action = Literal["submit", "approval", "skip"]
Outcome = Literal["pass", "fail", "review"]


@dataclass
class Check:
    name: str
    outcome: Outcome
    detail: str


@dataclass
class Decision:
    job_id: str
    title: str
    company: str
    portal: str | None
    score: float | None
    action: Action = "submit"
    checks: list[Check] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    resume_id: str | None = None

    def add(self, name: str, outcome: Outcome, detail: str) -> None:
        self.checks.append(Check(name, outcome, detail))
        if outcome == "fail":
            self.action = "skip"
        elif outcome == "review" and self.action == "submit":
            self.action = "approval"

    @property
    def reasons(self) -> list[str]:
        wanted = "fail" if self.action == "skip" else "review"
        return [c.detail for c in self.checks if c.outcome == wanted]


@dataclass
class Context:
    rules: AutomationRule
    profile: CandidateProfile
    submitted_today: int
    now: datetime


def get_rules(db: Session, user: User) -> AutomationRule:
    from app.schemas.settings import AutomationRulesIn

    rule = db.scalars(select(AutomationRule).where(AutomationRule.user_id == user.id)).first()
    if rule is None:
        rule = AutomationRule(user_id=user.id, **AutomationRulesIn().model_dump(mode="json"))
        db.add(rule)
        db.commit()
    return rule


def submitted_today(db: Session, user: User, now: datetime) -> int:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.user_id == user.id,
                Application.applied_via.in_(["simulated", "portal"]),
                Application.submitted_at >= start,
            )
        )
        or 0
    )


def _job_portal(db: Session, job: Job) -> Portal | None:
    src = db.scalars(select(JobSource).where(JobSource.job_id == job.id).order_by(JobSource.fetched_at)).first()
    return db.get(Portal, src.portal_id) if src else None


def _preferred_resume(db: Session, user: User, rules: AutomationRule, job: Job) -> tuple[Resume | None, str | None]:
    """Resume chosen by the first role keyword found in the job title. Returns (resume, problem)."""
    for keyword, resume_id in (rules.preferred_resume_by_role or {}).items():
        if keyword.lower() in job.title.lower():
            try:
                # Stored as JSON, so ids come back as strings.
                r = db.get(Resume, uuid.UUID(str(resume_id)))
            except ValueError:
                r = None
            if r is None or r.user_id != user.id:
                return None, f"Preferred resume for '{keyword}' no longer exists."
            return r, None
    return None, None


def evaluate(db: Session, user: User, ctx: Context, job: Job, match: JobMatch | None) -> Decision:
    rules = ctx.rules
    portal = _job_portal(db, job)
    d = Decision(
        job_id=str(job.id),
        title=job.title,
        company=job.company,
        portal=portal.code if portal else None,
        score=float(match.score) if match else None,
    )

    # 1. Master switches (reported so a dry run shows what would happen once enabled).
    d.add(
        "automation_enabled",
        "pass" if rules.enabled else "fail",
        "Automation is enabled." if rules.enabled else "Automation is turned off.",
    )
    d.add(
        "global_pause",
        "fail" if rules.global_pause else "pass",
        "Global pause is on." if rules.global_pause else "Not paused.",
    )

    # 2. Duplicates and listing state.
    existing = db.scalars(
        select(Application).where(Application.user_id == user.id, Application.job_id == job.id)
    ).first()
    if existing and existing.status not in {"draft", "prepared"}:
        d.add("duplicate", "fail", f"Already {existing.status}: not applying twice.")
    else:
        d.add("duplicate", "pass", "No previous application." if not existing else "Draft exists and will be reused.")
    if existing:
        earlier = db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.subject_type == "application",
                ApprovalRequest.subject_id == existing.id,
                ApprovalRequest.status.in_(["approved", "rejected"]),
            )
            .order_by(ApprovalRequest.decided_at.desc())
        ).first()
        if earlier is not None:
            # Respect the earlier human decision: never ask again or act on its own.
            d.add("earlier_decision", "fail", f"You {earlier.status} this application earlier.")
    if freshness(job.posted_at, job.expires_at, job.status, ctx.now) == "expired":
        d.add("listing_active", "fail", "The listing has expired.")

    # 3. Mandatory eligibility, separate from the score.
    elig = (match.eligibility if match else {}) or {}
    status = elig.get("status", "unknown")
    if status == "ineligible":
        d.add("eligibility", "fail", "Not eligible: " + " ".join(elig.get("reasons", [])))
    elif status == "unknown":
        d.add("eligibility", "review", "Eligibility unknown: " + (" ".join(elig.get("reasons", [])) or "not scored"))
    else:
        d.add("eligibility", "pass", "Eligible.")

    # 4. Score and job filters.
    if match is None or float(match.score) < rules.min_match_score:
        d.add("min_score", "fail", f"Score {d.score if d.score is not None else 'n/a'} below {rules.min_match_score}.")
    else:
        d.add("min_score", "pass", f"Score {d.score:g} ≥ {rules.min_match_score}.")
    if rules.allowed_titles:
        ok = any(t.lower() in job.title.lower() for t in rules.allowed_titles)
        d.add(
            "allowed_titles",
            "pass" if ok else "fail",
            "Title allowed." if ok else f"'{job.title}' matches none of the allowed titles.",
        )
    if rules.allowed_locations:
        loc = (job.location or "").lower()
        ok = any(
            x.lower() in loc or (x.lower() == "remote" and job.work_arrangement == "remote")
            for x in rules.allowed_locations
        )
        d.add(
            "allowed_locations",
            "pass" if ok else "fail",
            "Location allowed." if ok else f"'{job.location or 'unstated'}' is not an allowed location.",
        )
    ckey = company_key(job.company)
    if ckey in {company_key(c) for c in rules.company_blocklist}:
        d.add("company_blocklist", "fail", f"{job.company} is blocklisted.")
    if rules.company_allowlist and ckey not in {company_key(c) for c in rules.company_allowlist}:
        d.add("company_allowlist", "fail", f"{job.company} is not on the allowlist.")
    if rules.min_salary is not None:
        top = job.salary_max or job.salary_min
        if top is None:
            d.add("min_salary", "review", "Salary not disclosed; minimum salary cannot be confirmed.")
        elif top < rules.min_salary:
            d.add("min_salary", "fail", f"Salary up to {top:,} is below {rules.min_salary:,}.")
        else:
            d.add("min_salary", "pass", "Salary meets the minimum.")

    # 5. Portal permissions and capabilities.
    connector = get_connector(portal.code) if portal else None
    perm = (rules.portal_permissions or {}).get(portal.code if portal else "", {}) or {}
    if portal is None or connector is None:
        d.add("portal", "fail", "Source portal unknown.")
    else:
        if not perm.get("enabled", True):
            d.add("portal_enabled", "fail", f"Automation is disabled for {portal.name}.")
        if not connector.get_capabilities().submit_application:
            d.add(
                "portal_permits_submission",
                "review",
                f"{portal.name} does not permit automated submission: apply manually.",
            )
        elif not perm.get("auto_apply", False):
            d.add("auto_apply", "review", f"Auto-apply is off for {portal.name}; approval needed.")
        else:
            d.add("auto_apply", "pass", f"Auto-apply allowed for {portal.name}.")

    # 6. Daily limit.
    if ctx.submitted_today >= rules.max_applications_per_day:
        d.add("daily_limit", "fail", f"Daily limit of {rules.max_applications_per_day} reached; try again tomorrow.")

    # 7. Resume and screening answers (only worth checking if not already skipped).
    if d.action != "skip":
        resume, problem = _preferred_resume(db, user, rules, job)
        if problem:
            d.add("preferred_resume", "review", problem)
        d.resume_id = str(resume.id) if resume else None
        if connector is not None and connector.get_capabilities().prepare_application:
            prep = connector.prepare_application(_external_id(db, job, portal), d.resume_id or "")
            d.questions = [str(q) for q in prep.data.get("questions", [])][:30]
        if d.questions:
            answers = documents.build_screening_answers(ctx.profile, d.questions, job)["answers"]
            flagged = [a for a in answers if a["needs_confirmation"]]
            if flagged:
                d.add(
                    "screening_answers",
                    "review",
                    f"{len(flagged)} screening answer(s) need you: " + "; ".join(a["reason"] for a in flagged),
                )
            else:
                d.add("screening_answers", "pass", "All screening answers come from your profile.")
    return d


def _external_id(db: Session, job: Job, portal: Portal | None) -> str:
    if portal is None:
        return ""
    src = db.scalars(select(JobSource).where(JobSource.job_id == job.id, JobSource.portal_id == portal.id)).first()
    return src.external_id if src else ""


def candidates(db: Session, user: User) -> list[tuple[Job, JobMatch | None]]:
    match_service.rescore_all(db, user)
    matches = {m.job_id: m for m in db.scalars(select(JobMatch).where(JobMatch.user_id == user.id))}
    rows = [(j, matches.get(j.id)) for j in db.scalars(select(Job).where(Job.status == "active"))]
    rows.sort(key=lambda r: float(r[1].score) if r[1] else -1, reverse=True)
    return rows


def preview(db: Session, user: User) -> list[Decision]:
    """Dry run: decisions only, nothing is created or submitted."""
    now = datetime.now(UTC)
    ctx = Context(get_rules(db, user), profile_service.get_or_create(db, user), submitted_today(db, user, now), now)
    out = [evaluate(db, user, ctx, j, m) for j, m in candidates(db, user)]
    db.rollback()  # belt and braces: a preview never persists anything
    return out


# ---------------------------------------------------------------- execution


def _prepare_documents(db: Session, user: User, job: Job, d: Decision) -> tuple[str | None, str | None, str | None]:
    """Resume (preferred or tailored), cover letter and screening drafts. All from profile facts."""
    profile = profile_service.get_or_create(db, user)
    resume_id = d.resume_id
    if resume_id is None and profile.full_name.strip():
        r, _ = documents.save_generated_resume(db, user, documents.build_resume(profile, job), job)
        resume_id = str(r.id)
    letter, _ = documents.save_document(
        db,
        user,
        "cover_letter",
        documents.build_cover_letter(profile, job),
        job,
        f"Cover letter – {job.title}, {job.company}",
    )
    answers_id = None
    if d.questions:
        doc, _ = documents.save_document(
            db,
            user,
            "screening_answers",
            documents.build_screening_answers(profile, d.questions, job),
            job,
            f"Screening answers – {job.title}, {job.company}",
        )
        answers_id = str(doc.id)
    db.commit()
    return resume_id, str(letter.id), answers_id


def _ensure_application(db: Session, user: User, job: Job, resume_id: str | None, letter_id: str | None) -> Application:
    app = db.scalars(select(Application).where(Application.user_id == user.id, Application.job_id == job.id)).first()
    if app is None:
        app = applications.create(
            db,
            user,
            job.id,
            uuid.UUID(resume_id) if resume_id else None,
            uuid.UUID(letter_id) if letter_id else None,
            notes="Prepared by automation rules.",
        )
    return app


def _ensure_approval(
    db: Session, user: User, app: Application, d: Decision, answers_id: str | None, now: datetime
) -> tuple[ApprovalRequest, bool]:
    existing = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.user_id == user.id,
            ApprovalRequest.subject_type == "application",
            ApprovalRequest.subject_id == app.id,
            ApprovalRequest.status == "pending",
        )
    ).first()
    payload = {
        "job_id": d.job_id,
        "title": d.title,
        "company": d.company,
        "portal": d.portal,
        "score": d.score,
        "reasons": d.reasons,
        "checks": [asdict(c) for c in d.checks],
        "resume_id": str(app.resume_id) if app.resume_id else None,
        "cover_letter_id": str(app.cover_letter_id) if app.cover_letter_id else None,
        "screening_answers_id": answers_id,
    }
    if existing:
        existing.payload = payload  # refresh reasons; never create a second pending request
        return existing, False
    req = ApprovalRequest(
        user_id=user.id,
        kind="application_submission",
        subject_type="application",
        subject_id=app.id,
        payload=payload,
        status="pending",
        expires_at=now + APPROVAL_TTL,
    )
    db.add(req)
    db.flush()
    db.add(
        Notification(
            user_id=user.id,
            kind="approval",
            title="Approval needed",
            body=f"{d.title} at {d.company}: {d.reasons[0] if d.reasons else 'review required'}",
            link="/approvals",
            dedupe_key=f"approval:{req.id}",
        )
    )
    return req, True


def run(db: Session, user: User, trigger: str = "manual") -> TaskRun:
    run_ = tasks.start(db, user.id, KIND, trigger)
    if run_.status != "running":
        return run_
    now = datetime.now(UTC)
    result: dict[str, Any] = {
        "submitted": 0,
        "approvals_created": 0,
        "approvals_updated": 0,
        "skipped": 0,
        "decisions": [],
    }
    try:
        rules = get_rules(db, user)
        if not rules.enabled or rules.global_pause:
            result["state"] = "paused" if rules.global_pause else "disabled"
            return tasks.finish(db, run_, result)
        expire_stale(db, user, now)
        ctx = Context(rules, profile_service.get_or_create(db, user), submitted_today(db, user, now), now)
        for job, match in candidates(db, user):
            d = evaluate(db, user, ctx, job, match)
            result["decisions"].append({"job_id": d.job_id, "title": d.title, "action": d.action, "reasons": d.reasons})
            if d.action == "skip":
                result["skipped"] += 1
                continue
            resume_id, letter_id, answers_id = _prepare_documents(db, user, job, d)
            app = _ensure_application(db, user, job, resume_id, letter_id)
            if d.action == "submit":
                applications.simulate_submit(db, user, app, actor="automation")
                if app.status == "submitted":
                    result["submitted"] += 1
                    ctx.submitted_today += 1
                else:  # outcome uncertain: needs reconciliation, never a blind retry
                    _, _ = _ensure_approval(db, user, app, d, answers_id, now)
            else:
                _, created = _ensure_approval(db, user, app, d, answers_id, now)
                result["approvals_created" if created else "approvals_updated"] += 1
            db.commit()
            tasks.heartbeat(db, run_)
        result["decisions"] = result["decisions"][:100]
        result["state"] = "ran"
        return tasks.finish(db, run_, result)
    except Exception as exc:
        return tasks.fail(db, run_, f"{type(exc).__name__}: {exc}", result)


# ---------------------------------------------------------------- approvals


class ApprovalError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def expire_stale(db: Session, user: User, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    n = 0
    for req in db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.user_id == user.id, ApprovalRequest.status == "pending")
    ):
        app = db.get(Application, req.subject_id) if req.subject_id else None
        job = db.get(Job, app.job_id) if app else None
        expired = req.expires_at is not None and _aware(req.expires_at) <= now
        gone = app is None or job is None or freshness(job.posted_at, job.expires_at, job.status, now) == "expired"
        settled = app is not None and app.status not in {"draft", "prepared"}
        if expired or gone or settled:
            req.status = "expired"
            req.decided_at = now
            n += 1
    db.commit()
    return n


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _pending(db: Session, user: User, req_id: Any) -> ApprovalRequest:
    req = db.get(ApprovalRequest, req_id)
    if req is None or req.user_id != user.id:
        raise ApprovalError("Approval request not found", 404)
    expire_stale(db, user)
    if req.status != "pending":
        raise ApprovalError(f"This request is already {req.status}.", 409)
    return req


def approve(
    db: Session, user: User, req_id: Any, confirm_reviewed: bool, note: str | None
) -> tuple[ApprovalRequest, str]:
    if not confirm_reviewed:
        raise ApprovalError("Confirm that you reviewed the job, documents and flagged answers (confirm_reviewed).")
    req = _pending(db, user, req_id)
    app = db.get(Application, req.subject_id)
    assert app is not None
    portal = db.get(Portal, app.portal_id) if app.portal_id else None
    connector = get_connector(portal.code) if portal else None
    if connector is not None and connector.get_capabilities().submit_application and portal and portal.code == "mock":
        applications.simulate_submit(db, user, app, actor="approval")
        outcome = "Simulated submission done." if app.status == "submitted" else "Outcome unknown; reconcile it."
    else:
        # The portal does not allow automated submission: the user applies, then marks it submitted.
        if app.status == "draft":
            applications.update(db, user, app, status="prepared")
        outcome = "Marked prepared. Apply on the portal yourself, then mark it submitted in the tracker."
    req.status = "approved"
    req.decided_at = datetime.now(UTC)
    req.payload = {**req.payload, "decision_note": note, "outcome": outcome}
    db.commit()
    return req, outcome


def reject(db: Session, user: User, req_id: Any, note: str | None) -> ApprovalRequest:
    req = _pending(db, user, req_id)
    req.status = "rejected"
    req.decided_at = datetime.now(UTC)
    req.payload = {**req.payload, "decision_note": note}
    db.commit()
    return req

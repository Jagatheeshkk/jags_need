"""Application tracking.

An application is only ever marked 'submitted' when that really happened:
  * manual    - you applied on the portal yourself and confirmed it here explicitly
  * simulated - the mock connector (synthetic jobs only); flagged is_simulated everywhere
  * portal    - a verified integration (Phase 5; none exist yet)
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.registry import get_connector
from app.models import Application, ApplicationEvent, Document, Job, JobSource, Notification, Portal, Resume, User

FOLLOW_UP_AFTER = timedelta(days=7)

TRANSITIONS: dict[str, set[str]] = {
    "draft": {"prepared", "submitted", "withdrawn"},
    "prepared": {"draft", "submitted", "withdrawn"},
    "submitted": {"interviewing", "offer", "rejected", "withdrawn", "status_unknown"},
    "status_unknown": {"submitted", "failed", "withdrawn"},
    "interviewing": {"offer", "rejected", "withdrawn"},
    "offer": {"withdrawn"},
    "rejected": set(),
    "withdrawn": set(),
    "failed": {"draft"},
}
ACTIVE_FOLLOW_UP = {"submitted", "interviewing"}


class ApplicationError(Exception):
    def __init__(self, message: str, status: int = 400, existing_id: uuid.UUID | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.existing_id = existing_id


def _now() -> datetime:
    return datetime.now(UTC)


def _event(db: Session, app: Application, kind: str, frm: str | None, to: str | None, **details: Any) -> None:
    db.add(ApplicationEvent(application_id=app.id, event_type=kind, from_status=frm, to_status=to, details=details))


def _check_owned(db: Session, user: User, model: type, obj_id: uuid.UUID | None) -> None:
    if obj_id is None:
        return
    obj = db.get(model, obj_id)
    if obj is None or obj.user_id != user.id:
        raise ApplicationError(f"{model.__name__} not found", 404)


def create(
    db: Session,
    user: User,
    job_id: uuid.UUID,
    resume_id: uuid.UUID | None = None,
    cover_letter_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> Application:
    job = db.get(Job, job_id)
    if job is None:
        raise ApplicationError("Job not found", 404)
    existing = db.scalars(
        select(Application).where(Application.user_id == user.id, Application.job_id == job_id)
    ).first()
    if existing:
        raise ApplicationError("You already have an application for this job.", 409, existing.id)
    _check_owned(db, user, Resume, resume_id)
    _check_owned(db, user, Document, cover_letter_id)
    first_source = db.scalars(
        select(JobSource).where(JobSource.job_id == job_id).order_by(JobSource.fetched_at, JobSource.external_id)
    ).first()
    app = Application(
        user_id=user.id,
        job_id=job_id,
        portal_id=first_source.portal_id if first_source else None,
        resume_id=resume_id,
        cover_letter_id=cover_letter_id,
        notes=notes,
        status="draft",
        idempotency_key=f"application:{user.id}:{job_id}",
        is_simulated=False,
        applied_via="manual",
    )
    db.add(app)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent duplicate: the unique constraint is the final guard
        db.rollback()
        raise ApplicationError("You already have an application for this job.", 409) from exc
    _event(db, app, "created", None, "draft")
    db.commit()
    return app


def update(
    db: Session,
    user: User,
    app: Application,
    *,
    status: str | None = None,
    confirm_submitted: bool = False,
    notes: str | None = None,
    follow_up_at: datetime | None = None,
    clear_follow_up: bool = False,
    resume_id: uuid.UUID | None = None,
    cover_letter_id: uuid.UUID | None = None,
    fields_set: set[str] | None = None,
) -> Application:
    fields_set = fields_set or set()
    if "resume_id" in fields_set:
        _check_owned(db, user, Resume, resume_id)
        app.resume_id = resume_id
    if "cover_letter_id" in fields_set:
        _check_owned(db, user, Document, cover_letter_id)
        app.cover_letter_id = cover_letter_id
    if "notes" in fields_set:
        app.notes = notes
    if clear_follow_up:
        app.follow_up_at = None
    elif follow_up_at is not None:
        app.follow_up_at = follow_up_at
    if fields_set & {"resume_id", "cover_letter_id", "notes", "follow_up_at"} or clear_follow_up:
        _event(db, app, "updated", app.status, app.status, fields=sorted(fields_set - {"status"}))

    if status and status != app.status:
        if status not in TRANSITIONS.get(app.status, set()):
            raise ApplicationError(f"Cannot change status from {app.status} to {status}.", 409)
        if status == "submitted" and app.status in {"draft", "prepared"}:
            if not confirm_submitted:
                raise ApplicationError(
                    "Confirm that you submitted this application on the portal yourself (confirm_submitted).", 400
                )
            app.applied_via = "manual"
            app.submitted_at = _now()
            app.follow_up_at = app.follow_up_at or _now() + FOLLOW_UP_AFTER
        frm = app.status
        app.status = status
        _event(db, app, "status_changed", frm, status, by="user")
    db.commit()
    return app


def simulate_submit(db: Session, user: User, app: Application, actor: str = "user") -> Application:
    """Mock connector only. Never touches a real portal; the result is flagged simulated."""
    if app.status == "submitted" and app.is_simulated:
        return app  # idempotent
    job = db.get(Job, app.job_id)
    portal = db.get(Portal, app.portal_id) if app.portal_id else None
    if job is None or not job.is_synthetic or portal is None or portal.code != "mock":
        raise ApplicationError("Simulated submission is only available for synthetic mock-portal jobs.", 409)
    if app.status not in {"draft", "prepared"}:
        raise ApplicationError(f"Cannot submit an application that is {app.status}.", 409)
    connector = get_connector("mock")
    assert connector is not None
    result = connector.submit_application(str(app.id))
    frm = app.status
    if result.status == "succeeded":
        app.status, app.applied_via, app.is_simulated = "submitted", "simulated", True
        app.external_reference = result.reference
        app.submitted_at = _now()
        app.follow_up_at = app.follow_up_at or _now() + FOLLOW_UP_AFTER
    else:
        # Outcome not confirmed: never assume success. Reconcile before retrying.
        app.status = "status_unknown"
    _event(
        db,
        app,
        "submission",
        frm,
        app.status,
        simulated=result.simulated,
        message=result.message,
        reference=result.reference,
        by=actor,
    )
    db.commit()
    return app


def reconcile(db: Session, user: User, app: Application) -> Application:
    if app.status != "status_unknown":
        raise ApplicationError("Only applications with unknown status need reconciling.", 409)
    portal = db.get(Portal, app.portal_id) if app.portal_id else None
    connector = get_connector(portal.code) if portal else None
    if connector is None or not connector.get_capabilities().get_application_status:
        raise ApplicationError("This portal cannot report status. Check the portal and set the status yourself.", 409)
    result = connector.get_application_status(str(app.id))
    if result.status == "succeeded":
        app.status = "submitted"
        _event(db, app, "reconciled", "status_unknown", "submitted", simulated=result.simulated, message=result.message)
    else:
        _event(db, app, "reconcile_failed", "status_unknown", "status_unknown", message=result.message)
    db.commit()
    return app


def due_follow_ups(db: Session, user: User, now: datetime | None = None) -> list[Application]:
    now = now or _now()
    stmt = select(Application).where(
        Application.user_id == user.id,
        Application.status.in_(ACTIVE_FOLLOW_UP),
        Application.follow_up_at.is_not(None),
        Application.follow_up_at <= now,
    )
    return list(db.scalars(stmt))


def notify_due_follow_ups(db: Session, user: User) -> int:
    created = 0
    today = _now().date().isoformat()
    for app in due_follow_ups(db, user):
        key = f"followup:{app.id}:{today}"
        if db.scalars(select(Notification).where(Notification.dedupe_key == key)).first():
            continue
        job = db.get(Job, app.job_id)
        db.add(
            Notification(
                user_id=user.id,
                kind="follow_up",
                title="Follow-up due",
                body=f"{job.title} at {job.company}" if job else None,
                link=f"/applications?focus={app.id}",
                dedupe_key=key,
            )
        )
        created += 1
    if created:
        db.commit()
    return created

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Application, ApplicationEvent, Job, Portal
from app.schemas.documents import ApplicationEventOut, ApplicationIn, ApplicationOut, ApplicationPatch, AppStatus
from app.services import applications as svc
from app.services.normalize import as_utc

router = APIRouter(prefix="/applications", tags=["applications"])


def _out(db: DbSession, app: Application, with_events: bool = False) -> ApplicationOut:
    job = db.get(Job, app.job_id)
    portal = db.get(Portal, app.portal_id) if app.portal_id else None
    events = []
    if with_events:
        stmt = (
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == app.id)
            .order_by(ApplicationEvent.created_at)
        )
        events = [ApplicationEventOut.model_validate(e) for e in db.scalars(stmt)]
    due = bool(
        app.follow_up_at and app.status in svc.ACTIVE_FOLLOW_UP and as_utc(app.follow_up_at) <= datetime.now(UTC)
    )
    return ApplicationOut(
        id=app.id,
        job_id=app.job_id,
        job_title=job.title if job else "(job removed)",
        company=job.company if job else "",
        job_is_synthetic=bool(job and job.is_synthetic),
        portal=portal.code if portal else None,
        status=app.status,
        applied_via=app.applied_via,
        is_simulated=app.is_simulated,
        external_reference=app.external_reference,
        submitted_at=app.submitted_at,
        follow_up_at=app.follow_up_at,
        follow_up_due=due,
        resume_id=app.resume_id,
        cover_letter_id=app.cover_letter_id,
        notes=app.notes,
        created_at=app.created_at,
        allowed_next=sorted(svc.TRANSITIONS.get(app.status, set())),
        events=events,
    )


def _get(db: DbSession, user: CurrentUser, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Application not found")
    return app


def _raise(exc: svc.ApplicationError) -> HTTPException:
    detail: dict | str = str(exc)
    if exc.existing_id:
        detail = {"message": str(exc), "existing_id": str(exc.existing_id)}
    return HTTPException(exc.status, detail=detail)


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    user: CurrentUser,
    db: DbSession,
    status_filter: AppStatus | None = Query(None, alias="status"),
    job_id: uuid.UUID | None = None,
) -> list[ApplicationOut]:
    svc.notify_due_follow_ups(db, user)
    stmt = select(Application).where(Application.user_id == user.id)
    if status_filter:
        stmt = stmt.where(Application.status == status_filter)
    if job_id:
        stmt = stmt.where(Application.job_id == job_id)
    return [_out(db, a) for a in db.scalars(stmt.order_by(Application.updated_at.desc()))]


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(body: ApplicationIn, user: CurrentUser, db: DbSession) -> ApplicationOut:
    try:
        app = svc.create(db, user, body.job_id, body.resume_id, body.cover_letter_id, body.notes)
    except svc.ApplicationError as exc:
        raise _raise(exc) from exc
    return _out(db, app, with_events=True)


@router.get("/{app_id}", response_model=ApplicationOut)
def get_application(app_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationOut:
    return _out(db, _get(db, user, app_id), with_events=True)


@router.patch("/{app_id}", response_model=ApplicationOut)
def patch_application(app_id: uuid.UUID, body: ApplicationPatch, user: CurrentUser, db: DbSession) -> ApplicationOut:
    app = _get(db, user, app_id)
    fields = set(body.model_fields_set)
    try:
        svc.update(
            db,
            user,
            app,
            status=body.status,
            confirm_submitted=body.confirm_submitted,
            notes=body.notes,
            follow_up_at=body.follow_up_at,
            clear_follow_up="follow_up_at" in fields and body.follow_up_at is None,
            resume_id=body.resume_id,
            cover_letter_id=body.cover_letter_id,
            fields_set=fields,
        )
    except svc.ApplicationError as exc:
        raise _raise(exc) from exc
    return _out(db, app, with_events=True)


@router.post("/{app_id}/simulate-submit", response_model=ApplicationOut)
def simulate_submit(app_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationOut:
    try:
        app = svc.simulate_submit(db, user, _get(db, user, app_id))
    except svc.ApplicationError as exc:
        raise _raise(exc) from exc
    return _out(db, app, with_events=True)


@router.post("/{app_id}/reconcile", response_model=ApplicationOut)
def reconcile(app_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationOut:
    try:
        app = svc.reconcile(db, user, _get(db, user, app_id))
    except svc.ApplicationError as exc:
        raise _raise(exc) from exc
    return _out(db, app, with_events=True)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    app = _get(db, user, app_id)
    if app.status not in {"draft", "prepared"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Only drafts can be deleted; withdraw a submitted application instead."
        )
    db.delete(app)
    db.commit()

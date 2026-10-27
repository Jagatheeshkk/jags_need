import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models import Portal, ProfileSyncRun
from app.services import audit, profile_sync

router = APIRouter(prefix="/profile-sync", tags=["profile-sync"])


class SyncRunOut(BaseModel):
    id: uuid.UUID
    portal: str
    status: str
    preview: dict[str, Any]
    result: dict[str, Any]
    attempts: int
    created_at: datetime
    finished_at: datetime | None


class ConfirmIn(BaseModel):
    confirm_updated: bool = False


def _out(db: Session, run: ProfileSyncRun) -> SyncRunOut:
    portal = db.get(Portal, run.portal_id)
    return SyncRunOut(
        id=run.id,
        portal=portal.code if portal else "?",
        status=run.status,
        preview=run.preview,
        result=run.result,
        attempts=run.attempts,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _call[T](fn: Callable[..., T], *args: Any) -> T:
    try:
        return fn(*args)
    except profile_sync.SyncError as exc:
        raise HTTPException(exc.status, detail=str(exc)) from exc


@router.get("/runs", response_model=list[SyncRunOut])
def runs(user: CurrentUser, db: DbSession, portal: str | None = None) -> list[SyncRunOut]:
    return [_out(db, r) for r in _call(profile_sync.history, db, user, portal)]


@router.get("/{code}/preview")
def preview(code: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return _call(profile_sync.preview, db, user, code)


@router.post("/{code}/prepare", response_model=SyncRunOut, status_code=status.HTTP_201_CREATED)
def prepare(code: str, request: Request, response: Response, user: CurrentUser, db: DbSession) -> SyncRunOut:
    run, created = _call(profile_sync.prepare, db, user, code)
    if created:
        audit.record(
            db,
            "profile_sync.prepared",
            user_id=user.id,
            entity_type="profile_sync_run",
            entity_id=run.id,
            details={"portal": code},
            request=request,
        )
        db.commit()
    else:
        response.status_code = status.HTTP_200_OK
    return _out(db, run)


@router.post("/runs/{run_id}/confirm", response_model=SyncRunOut)
def confirm(run_id: uuid.UUID, body: ConfirmIn, request: Request, user: CurrentUser, db: DbSession) -> SyncRunOut:
    run = _call(profile_sync.confirm_manual, db, user, run_id, body.confirm_updated)
    audit.record(
        db,
        "profile_sync.confirmed_manual",
        user_id=user.id,
        entity_type="profile_sync_run",
        entity_id=run.id,
        request=request,
    )
    db.commit()
    return _out(db, run)


@router.post("/runs/{run_id}/run", response_model=SyncRunOut)
def run_automated(run_id: uuid.UUID, request: Request, user: CurrentUser, db: DbSession) -> SyncRunOut:
    run = _call(profile_sync.run_automated, db, user, run_id)
    audit.record(
        db,
        "profile_sync.automated",
        user_id=user.id,
        entity_type="profile_sync_run",
        entity_id=run.id,
        details={"status": run.status, "simulated": run.result.get("simulated")},
        request=request,
    )
    db.commit()
    return _out(db, run)


@router.post("/runs/{run_id}/cancel", response_model=SyncRunOut)
def cancel(run_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SyncRunOut:
    return _out(db, _call(profile_sync.cancel, db, user, run_id))

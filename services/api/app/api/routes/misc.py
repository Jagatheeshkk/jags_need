"""Overview, notifications, audit log, data export/deletion and health."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text, update

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.api.routes.auth import _clear_session
from app.models import Application, ApprovalRequest, AuditLog, Job, JobMatch, Notification
from app.schemas.auth import DeleteAccountRequest
from app.security.passwords import verify_password
from app.services import data_service, portal_service, profile_service

router = APIRouter(tags=["misc"])


@router.get("/health")
def health(db: DbSession) -> JSONResponse:
    """Unauthenticated liveness probe used to wake a sleeping free instance."""
    try:
        db.execute(text("SELECT 1"))
        db_state = "ok"
    except Exception:  # noqa: BLE001
        db_state = "unavailable"
    code = status.HTTP_200_OK if db_state == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        {
            "status": "ok" if db_state == "ok" else "degraded",
            "database": db_state,
            "time": datetime.now(UTC).isoformat(),
        },
        status_code=code,
    )


@router.get("/overview")
def overview(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Counts straight from the database; nothing here is estimated or fabricated."""
    profile = profile_service.get_or_create(db, user)

    def count(stmt: Any) -> int:
        return int(db.scalar(stmt) or 0)

    apps_by_status = dict(
        db.execute(
            select(Application.status, func.count()).where(Application.user_id == user.id).group_by(Application.status)
        ).all()
    )
    portals = portal_service.list_for_user(db, user)
    return {
        "profile_completeness": profile_service.completeness(profile).model_dump(),
        "jobs": {
            "real": count(select(func.count()).select_from(Job).where(Job.is_synthetic.is_(False))),
            "synthetic": count(select(func.count()).select_from(Job).where(Job.is_synthetic.is_(True))),
        },
        "saved_jobs": count(
            select(func.count()).select_from(JobMatch).where(JobMatch.user_id == user.id, JobMatch.is_saved.is_(True))
        ),
        "applications": apps_by_status,
        "pending_approvals": count(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.user_id == user.id, ApprovalRequest.status == "pending")
        ),
        "unread_notifications": count(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        ),
        "portals": [{"code": p.code, "name": p.name, "status": p.status} for p in portals],
    }


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(user: CurrentUser, db: DbSession, unread_only: bool = False) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(100)))


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notification not found")
    n.read_at = n.read_at or datetime.now(UTC)
    db.commit()


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(user: CurrentUser, db: DbSession) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any]
    created_at: datetime


@router.get("/audit", response_model=list[AuditOut])
def audit_log(user: CurrentUser, db: DbSession, limit: int = 50) -> list[AuditLog]:
    limit = max(1, min(limit, 200))
    stmt = select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/data/export")
def export_data(user: CurrentUser, db: DbSession) -> JSONResponse:
    payload = data_service.export_user_data(db, user)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": f'attachment; filename="ai-job-agent-export-{stamp}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/data/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_data(
    body: DeleteAccountRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> None:
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Password is incorrect")
    data_service.delete_user_data(db, user)
    _clear_session(response, settings)

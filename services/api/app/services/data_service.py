"""Personal data export and deletion."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    ApprovalRequest,
    AuditLog,
    AutomationRule,
    JobMatch,
    Notification,
    PortalConnection,
    ProfileSyncRun,
    Resume,
    User,
)
from app.services import profile_service


def _row(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    exclude = exclude or set()
    out = {}
    for col in obj.__table__.columns:
        if col.key in exclude:
            continue
        val = getattr(obj, col.key)
        out[col.key] = (
            val.isoformat()
            if hasattr(val, "isoformat")
            else (str(val) if val is not None and not isinstance(val, (int, float, bool, str, list, dict)) else val)
        )
    return out


def export_user_data(db: Session, user: User) -> dict[str, Any]:
    profile = profile_service.get_or_create(db, user)
    uid = user.id

    def rows(model: Any, exclude: set[str] | None = None) -> list[dict[str, Any]]:
        return [_row(r, exclude) for r in db.scalars(select(model).where(model.user_id == uid))]

    return {
        "export_format": "ai-job-agent/v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "user": _row(user, exclude={"password_hash", "session_version"}),
        "profile": profile_service.to_out(profile).model_dump(mode="json"),
        "automation_rules": rows(AutomationRule),
        "portal_connections": rows(PortalConnection),
        # File bytes are downloadable separately; metadata and hashes are included here.
        "resumes": rows(Resume, exclude={"content"}),
        "job_matches": rows(JobMatch),
        "applications": rows(Application),
        "profile_sync_runs": rows(ProfileSyncRun),
        "approval_requests": rows(ApprovalRequest),
        "notifications": rows(Notification),
        "audit_logs": rows(AuditLog, exclude={"ip_hash"}),
    }


def delete_user_data(db: Session, user: User) -> None:
    """Delete the owner account and everything linked to it (FK cascades), plus its audit trail."""
    db.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    db.delete(user)
    db.commit()

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk, utcnow


class Application(UUIDPk, Timestamps, Base):
    __tablename__ = "applications"
    # One application per job per user: database-level duplicate prevention.
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    portal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("portals.id"))
    resume_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="SET NULL"))
    # draft | prepared | pending_approval | submitting | submitted | status_unknown | failed | withdrawn
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(200))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ApplicationEvent(UUIDPk, Base):
    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AutomationRule(UUIDPk, Timestamps, Base):
    __tablename__ = "automation_rules"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Safe defaults: automation is off and paused until the user opts in.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    global_pause: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=75)
    allowed_titles: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    allowed_locations: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    company_allowlist: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    company_blocklist: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    max_applications_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # {"naukri": {"auto_apply": false, "enabled": true}, ...}
    portal_permissions: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    preferred_resume_by_role: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    score_weights: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)


class ProfileSyncRun(UUIDPk, Timestamps, Base):
    __tablename__ = "profile_sync_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    portal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("portals.id"), nullable=False)
    # preview | pending_approval | running | succeeded | failed | manual_required
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="preview")
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    preview: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRequest(UUIDPk, Timestamps, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (Index("ix_approval_requests_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    # Lets background jobs create a notification at most once per event.
    dedupe_key: Mapped[str | None] = mapped_column(String(150), unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(UUIDPk, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_user_created", "user_id", "created_at"),)

    # Nullable + SET NULL so failed-login events survive and account deletion keeps no link.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    # Field names that changed, never full personal values.
    details: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TaskRun(UUIDPk, Base):
    """Persistent state for background work (job refresh, rescoring).

    Free hosting can sleep or restart mid-task, so state lives in the database: a run left
    'running' without a recent heartbeat is marked 'interrupted' and can be retried safely.
    """

    __tablename__ = "task_runs"
    __table_args__ = (Index("ix_task_runs_user_kind_created", "user_id", "kind", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    # running | succeeded | failed | interrupted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    idempotency_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

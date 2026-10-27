"""Database-backed task state.

No Redis or always-on worker: tasks run inside the request or CLI call that starts them, and
their state is persisted so a run cut off by a free-tier sleep/restart is detected and can be
retried safely.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import TaskRun

STALE_AFTER = timedelta(minutes=10)


class TaskAlreadyRunning(Exception):
    def __init__(self, run: TaskRun) -> None:
        super().__init__(f"{run.kind} is already running")
        self.run = run


def _now() -> datetime:
    return datetime.now(UTC)


def recover_stale(db: Session, now: datetime | None = None) -> int:
    """Mark runs whose worker vanished (no heartbeat for STALE_AFTER) as interrupted."""
    cutoff = (now or _now()) - STALE_AFTER
    result = db.execute(
        update(TaskRun)
        .where(TaskRun.status == "running", TaskRun.heartbeat_at < cutoff)
        .values(
            status="interrupted",
            finished_at=now or _now(),
            error="Interrupted: the server slept or restarted before the task finished. Safe to retry.",
        )
    )
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def start(db: Session, user_id: uuid.UUID, kind: str, trigger: str = "manual", key: str | None = None) -> TaskRun:
    recover_stale(db)
    running = db.scalars(
        select(TaskRun).where(TaskRun.user_id == user_id, TaskRun.kind == kind, TaskRun.status == "running")
    ).first()
    if running is not None:
        raise TaskAlreadyRunning(running)
    run = TaskRun(
        user_id=user_id,
        kind=kind,
        trigger=trigger,
        status="running",
        idempotency_key=key or f"{kind}:{user_id}:{uuid.uuid4()}",
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        # Same idempotency key already used: return that run instead of doing the work twice.
        db.rollback()
        existing = db.scalars(select(TaskRun).where(TaskRun.idempotency_key == key)).one()
        if existing.status == "running":
            raise TaskAlreadyRunning(existing) from None
        return existing
    return run


def heartbeat(db: Session, run: TaskRun) -> None:
    run.heartbeat_at = _now()
    db.commit()


def finish(db: Session, run: TaskRun, result: dict[str, Any]) -> TaskRun:
    run.status = "succeeded"
    run.result = result
    run.finished_at = run.heartbeat_at = _now()
    db.commit()
    return run


def fail(db: Session, run: TaskRun, error: str, result: dict[str, Any] | None = None) -> TaskRun:
    db.rollback()
    run.status = "failed"
    run.error = error[:2000]
    run.result = result or {}
    run.finished_at = run.heartbeat_at = _now()
    db.commit()
    return run


def latest(db: Session, user_id: uuid.UUID, kind: str, status: str | None = None) -> TaskRun | None:
    stmt = select(TaskRun).where(TaskRun.user_id == user_id, TaskRun.kind == kind)
    if status:
        stmt = stmt.where(TaskRun.status == status)
    return db.scalars(stmt.order_by(TaskRun.created_at.desc()).limit(1)).first()

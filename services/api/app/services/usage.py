"""Storage usage against the free database plan's quota.

Neon Free blocks writes once a project reaches its storage limit, and resumes are stored in the
database, so the app warns well before that point.
"""

from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Application, Document, Job, Notification, Resume, TaskRun

WARN_AT = 70.0
FAIL_AT = 90.0

Status = Literal["ok", "warn", "fail", "info"]


def classify(percent: float) -> Status:
    return "fail" if percent >= FAIL_AT else "warn" if percent >= WARN_AT else "ok"


def report(db: Session, settings: Settings) -> dict[str, Any]:
    counts = {
        name: int(db.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in (
            ("jobs", Job),
            ("resumes", Resume),
            ("documents", Document),
            ("applications", Application),
            ("notifications", Notification),
            ("task_runs", TaskRun),
        )
    }
    resume_bytes = int(
        db.scalar(select(func.coalesce(func.sum(Resume.size_bytes), 0)).where(Resume.content.is_not(None))) or 0
    )
    limit = settings.db_storage_limit_mb * 1024 * 1024
    out: dict[str, Any] = {
        "database": db.get_bind().dialect.name,
        "limit_bytes": limit,
        "uploaded_resume_bytes": resume_bytes,
        "row_counts": counts,
        "used_bytes": None,
        "used_percent": None,
        "largest_tables": [],
    }
    if out["database"] != "postgresql":
        out["status"] = "info"
        out["detail"] = "Storage is measured on PostgreSQL only (this is a local SQLite database)."
        return out

    used = int(db.scalar(text("SELECT pg_database_size(current_database())")) or 0)
    tables = db.execute(
        text(
            "SELECT relname, pg_total_relation_size(relid) AS bytes FROM pg_stat_user_tables "
            "ORDER BY bytes DESC LIMIT 6"
        )
    ).all()
    pct = round(used * 100 / limit, 1)
    status = classify(pct)
    out.update(
        used_bytes=used,
        used_percent=pct,
        largest_tables=[{"table": r[0], "bytes": int(r[1])} for r in tables],
        status=status,
        detail=(
            f"{used / 1048576:.1f} MB of {settings.db_storage_limit_mb} MB used ({pct}%). "
            + (
                "Writes stop at 100% on Neon Free: export and delete old resumes, or archive data."
                if status != "ok"
                else "Within the free plan."
            )
        ),
    )
    return out

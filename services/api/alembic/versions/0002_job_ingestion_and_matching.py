"""job ingestion and matching

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27 21:32:12.227667
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

# Frozen copy of app.services.normalize.company_key at the time of this migration, so the
# backfill never changes if that function evolves later.
_SUFFIXES = {"ltd", "limited", "pvt", "private", "inc", "llc", "llp", "corp", "corporation", "co", "plc", "gmbh"}


def _company_key(name: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    while words and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=150), nullable=False),
        sa.Column("result", JSON, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_task_runs_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_runs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_task_runs_idempotency_key")),
    )
    op.create_index("ix_task_runs_user_kind_created", "task_runs", ["user_id", "kind", "created_at"], unique=False)

    # Server defaults let the NOT NULL columns be added to tables that already have rows.
    op.add_column(
        "candidate_profiles", sa.Column("search_keywords", JSON, nullable=False, server_default=sa.text("'[]'"))
    )
    op.add_column(
        "candidate_profiles",
        sa.Column("refresh_interval_hours", sa.Integer(), nullable=False, server_default=sa.text("24")),
    )
    op.add_column("jobs", sa.Column("company_key", sa.String(length=200), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("skills", JSON, nullable=False, server_default=sa.text("'[]'")))
    op.add_column("jobs", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_jobs_company_key"), "jobs", ["company_key"], unique=False)

    conn = op.get_bind()
    jobs = sa.table(
        "jobs", sa.column("id", sa.Uuid()), sa.column("company", sa.String()), sa.column("company_key", sa.String())
    )
    for row in conn.execute(sa.select(jobs.c.id, jobs.c.company)).all():
        conn.execute(sa.update(jobs).where(jobs.c.id == row.id).values(company_key=_company_key(row.company)))


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_company_key"), table_name="jobs")
    op.drop_column("jobs", "last_seen_at")
    op.drop_column("jobs", "skills")
    op.drop_column("jobs", "company_key")
    op.drop_column("candidate_profiles", "refresh_interval_hours")
    op.drop_column("candidate_profiles", "search_keywords")
    op.drop_index("ix_task_runs_user_kind_created", table_name="task_runs")
    op.drop_table("task_runs")

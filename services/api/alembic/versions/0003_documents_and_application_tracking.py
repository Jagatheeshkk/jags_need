"""documents and application tracking

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", JSON, nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_documents_job_id_jobs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_documents_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("user_id", "sha256", name=op.f("uq_documents_user_id_sha256")),
    )
    op.create_index("ix_documents_user_kind_job", "documents", ["user_id", "kind", "job_id"], unique=False)

    # batch_alter_table: plain ALTERs on PostgreSQL, table rebuild on SQLite (needed for new FKs).
    with op.batch_alter_table("applications") as b:
        b.add_column(sa.Column("cover_letter_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("applied_via", sa.String(length=20), nullable=False, server_default="manual"))
        b.create_foreign_key(
            op.f("fk_applications_cover_letter_id_documents"),
            "documents",
            ["cover_letter_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("resumes") as b:
        b.add_column(sa.Column("job_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("content_json", JSON, nullable=True))
        b.create_foreign_key(op.f("fk_resumes_job_id_jobs"), "jobs", ["job_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("resumes") as b:
        b.drop_constraint(op.f("fk_resumes_job_id_jobs"), type_="foreignkey")
        b.drop_column("content_json")
        b.drop_column("job_id")
    with op.batch_alter_table("applications") as b:
        b.drop_constraint(op.f("fk_applications_cover_letter_id_documents"), type_="foreignkey")
        b.drop_column("applied_via")
        b.drop_column("cover_letter_id")
    op.drop_index("ix_documents_user_kind_job", table_name="documents")
    op.drop_table("documents")

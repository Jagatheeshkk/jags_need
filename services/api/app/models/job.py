import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk, utcnow


class Job(UUIDPk, Timestamps, Base):
    __tablename__ = "jobs"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    # Normalised company name; narrows the content-similarity duplicate search.
    company_key: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    location: Mapped[str | None] = mapped_column(String(200))
    work_arrangement: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    experience_min: Mapped[int | None] = mapped_column(Integer)
    experience_max: Mapped[int | None] = mapped_column(Integer)
    canonical_url: Mapped[str | None] = mapped_column(String(1000), unique=True)
    # sha256 of normalised title|company|location|description, used for duplicate detection.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Skills listed by the source, when it provides structured skills.
    skills: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # True for mock-connector data so it is never presented as a real listing.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class JobSource(UUIDPk, Base):
    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("portal_id", "external_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    portal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("portals.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class JobMatch(UUIDPk, Timestamps, Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        Index("ix_job_matches_user_score", "user_id", "score"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    matched_skills: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    missing_skills: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    eligibility: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(String(30), nullable=False, default="rule_based")
    is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feedback: Mapped[str | None] = mapped_column(String(20))


class Resume(UUIDPk, Timestamps, Base):
    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("user_id", "sha256"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    # uploaded (your own file) | master (generated from profile) | tailored (generated for a job)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="master")
    parent_resume_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="SET NULL"))
    target_role: Mapped[str | None] = mapped_column(String(200))
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Database-backed storage keeps everything inside the free Postgres plan (no object store).
    content: Mapped[bytes | None] = mapped_column(LargeBinary)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    # Structured content of generated resumes; DOCX and PDF are rendered from it on download.
    content_json: Mapped[dict[str, Any] | None] = mapped_column()


class Document(UUIDPk, Timestamps, Base):
    """Generated cover letters and screening-answer drafts, versioned like resumes."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("user_id", "sha256"),
        Index("ix_documents_user_kind_job", "user_id", "kind", "job_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="SET NULL"))
    # cover_letter | screening_answers
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    # sha256 of the canonical content: identical regenerations return the existing version.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

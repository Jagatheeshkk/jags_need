import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk


class CandidateProfile(UUIDPk, Timestamps, Base):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(200))
    headline: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    total_experience_years: Mapped[float | None] = mapped_column(Numeric(4, 1))

    # Job preferences
    preferred_roles: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    preferred_locations: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    work_arrangement: Mapped[str] = mapped_column(String(20), default="any", nullable=False)
    salary_currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    excluded_companies: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    target_experience_min: Mapped[int | None] = mapped_column(Integer)
    target_experience_max: Mapped[int | None] = mapped_column(Integer)

    education: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    certifications: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    links: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    employment: Mapped[list["EmploymentHistory"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="(EmploymentHistory.sort_order, EmploymentHistory.start_date.desc())",
    )
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class EmploymentHistory(UUIDPk, Timestamps, Base):
    __tablename__ = "employment_history"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    achievements: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped[CandidateProfile] = relationship(back_populates="employment")


class Skill(UUIDPk, Base):
    __tablename__ = "skills"

    # Lower-cased canonical name, e.g. "playwright".
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))


class CandidateSkill(UUIDPk, Timestamps, Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("profile_id", "skill_id"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False)
    level: Mapped[str | None] = mapped_column(String(20))
    years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    profile: Mapped[CandidateProfile] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(lazy="joined")

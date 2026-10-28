import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Feedback = Literal["good_match", "poor_match"]


class TaskRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    trigger: str
    result: dict[str, Any]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class MatchOut(BaseModel):
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    eligibility: dict[str, Any]
    components: dict[str, Any]
    engine: str
    is_saved: bool
    feedback: str | None


class JobSummary(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location: str | None
    work_arrangement: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    experience_min: int | None
    experience_max: int | None
    posted_at: datetime | None
    expires_at: datetime | None
    last_seen_at: datetime | None
    status: str
    freshness: str
    is_synthetic: bool
    source_count: int
    match: MatchOut | None


class JobSourceOut(BaseModel):
    portal: str
    external_id: str
    url: str | None
    fetched_at: datetime


class JobDetail(JobSummary):
    description: str | None
    skills: list[str]
    canonical_url: str | None
    sources: list[JobSourceOut]
    explanation: str | None


class JobList(BaseModel):
    items: list[JobSummary]
    total: int
    last_refresh: TaskRunOut | None
    refresh_due: bool


class SavedIn(BaseModel):
    saved: bool


class FeedbackIn(BaseModel):
    feedback: Feedback | None


class ManualJobIn(BaseModel):
    """A listing the user copied from a manual-only portal. The URL is never fetched."""

    model_config = ConfigDict(extra="forbid")

    portal: Literal["linkedin", "indeed", "naukri", "instahyre", "cutshort"]
    # Scheme is case-insensitive (RFC 3986); hosts are checked by the connector after lower-casing.
    url: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^(?i:https)://", max_length=1000)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=300)]
    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    location: str | None = Field(default=None, max_length=200)
    work_arrangement: Literal["remote", "hybrid", "onsite"] | None = None
    description: str | None = Field(default=None, max_length=20000)
    skills: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=50
    )
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    experience_min: int | None = Field(default=None, ge=0, le=60)
    experience_max: int | None = Field(default=None, ge=0, le=60)
    posted_at: datetime | None = None
    expires_at: datetime | None = None


class ManualJobOut(BaseModel):
    job_id: uuid.UUID
    outcome: Literal["created", "updated", "merged"]

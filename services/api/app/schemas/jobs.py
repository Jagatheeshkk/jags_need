import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

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

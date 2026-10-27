import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.profile import EducationItem, ProfileUpdate

Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    kind: str
    version: int
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    target_role: str | None
    job_id: uuid.UUID | None
    parent_resume_id: uuid.UUID | None
    created_at: datetime


class ResumeDetail(ResumeOut):
    content_json: dict[str, Any] | None
    has_text: bool


class UploadResult(BaseModel):
    resume: ResumeOut
    duplicate: bool
    suggestions: dict[str, Any]


class ApplySuggestionsIn(BaseModel):
    """Only what the user ticked after reviewing the extracted values."""

    model_config = ConfigDict(extra="forbid")

    profile: ProfileUpdate = Field(default_factory=ProfileUpdate)
    add_skills: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100
    )
    add_education: list[EducationItem] = Field(default_factory=list, max_length=20)


class GenerateResumeIn(BaseModel):
    job_id: uuid.UUID | None = None


class GeneratedResume(BaseModel):
    resume: ResumeOut
    created: bool


class CoverLetterIn(BaseModel):
    job_id: uuid.UUID


class ScreeningIn(BaseModel):
    job_id: uuid.UUID | None = None
    questions: list[Text500] = Field(min_length=1, max_length=30)


class CoverLetterEdit(BaseModel):
    """Edited cover letter text. Saved as a new version; the previous one is kept."""

    model_config = ConfigDict(extra="forbid")

    greeting: Text500
    paragraphs: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]] = Field(
        min_length=1, max_length=12
    )
    sign_off: Text500


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    title: str
    version: int
    job_id: uuid.UUID | None
    sha256: str
    content: dict[str, Any]
    created_at: datetime


class GeneratedDocument(BaseModel):
    document: DocumentOut
    created: bool


AppStatus = Literal[
    "draft", "prepared", "submitted", "interviewing", "offer", "rejected", "withdrawn", "status_unknown", "failed"
]


class ApplicationIn(BaseModel):
    job_id: uuid.UUID
    resume_id: uuid.UUID | None = None
    cover_letter_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ApplicationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AppStatus | None = None
    # Required when marking a draft as submitted: you applied on the portal yourself.
    confirm_submitted: bool = False
    notes: str | None = Field(default=None, max_length=5000)
    follow_up_at: datetime | None = None
    resume_id: uuid.UUID | None = None
    cover_letter_id: uuid.UUID | None = None


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    from_status: str | None
    to_status: str | None
    details: dict[str, Any]
    created_at: datetime


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company: str
    job_is_synthetic: bool
    portal: str | None
    status: str
    applied_via: str
    is_simulated: bool
    external_reference: str | None
    submitted_at: datetime | None
    follow_up_at: datetime | None
    follow_up_due: bool
    resume_id: uuid.UUID | None
    cover_letter_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    allowed_next: list[str]
    events: list[ApplicationEventOut] = []

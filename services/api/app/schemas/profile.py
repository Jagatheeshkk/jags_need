import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

WorkArrangement = Literal["remote", "hybrid", "onsite", "any"]
SkillLevel = Literal["beginner", "intermediate", "advanced", "expert"]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for v in values:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


class EducationItem(BaseModel):
    institution: ShortText
    degree: ShortText
    field_of_study: str | None = Field(default=None, max_length=200)
    start_year: int | None = Field(default=None, ge=1950, le=2100)
    end_year: int | None = Field(default=None, ge=1950, le=2100)


class CertificationItem(BaseModel):
    name: ShortText
    issuer: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=1950, le=2100)


class ProfileUpdate(BaseModel):
    """Partial update; only fields present in the request are changed."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^[0-9+()\-\s]{6,40}$")] | None = None
    location: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=5000)
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
    preferred_roles: list[ShortText] | None = Field(default=None, max_length=30)
    preferred_locations: list[ShortText] | None = Field(default=None, max_length=30)
    work_arrangement: WorkArrangement | None = None
    salary_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    excluded_companies: list[ShortText] | None = Field(default=None, max_length=200)
    target_experience_min: int | None = Field(default=None, ge=0, le=60)
    target_experience_max: int | None = Field(default=None, ge=0, le=60)
    search_keywords: list[ShortText] | None = Field(default=None, max_length=20)
    refresh_interval_hours: int | None = Field(default=None, ge=1, le=168)
    education: list[EducationItem] | None = Field(default=None, max_length=20)
    certifications: list[CertificationItem] | None = Field(default=None, max_length=50)
    links: dict[str, Annotated[str, StringConstraints(max_length=500)]] | None = None

    @field_validator("preferred_roles", "preferred_locations", "excluded_companies", "search_keywords")
    @classmethod
    def _unique(cls, v: list[str] | None) -> list[str] | None:
        return _dedupe(v) if v is not None else None

    @field_validator("links")
    @classmethod
    def _links_https(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v:
            if len(v) > 10:
                raise ValueError("At most 10 links")
            for url in v.values():
                if not url.startswith("https://"):
                    raise ValueError("Links must start with https://")
        return v

    @model_validator(mode="after")
    def _ranges(self) -> "ProfileUpdate":
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min cannot exceed salary_max")
        lo, hi = self.target_experience_min, self.target_experience_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("target_experience_min cannot exceed target_experience_max")
        return self


class EmploymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: ShortText
    title: ShortText
    location: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = Field(default=None, max_length=5000)
    achievements: list[Annotated[str, StringConstraints(max_length=500)]] = Field(default_factory=list, max_length=20)
    sort_order: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def _dates(self) -> "EmploymentIn":
        if self.start_date > date.today():
            raise ValueError("start_date cannot be in the future")
        if self.is_current and self.end_date is not None:
            raise ValueError("A current role cannot have an end_date")
        if not self.is_current and self.end_date is None:
            raise ValueError("end_date is required unless is_current is true")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class EmploymentOut(EmploymentIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

    @model_validator(mode="after")
    def _dates(self) -> "EmploymentOut":  # stored rows were validated on write
        return self


class SkillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    level: SkillLevel | None = None
    years_experience: float | None = Field(default=None, ge=0, le=60)
    is_primary: bool = False


class SkillOut(BaseModel):
    id: uuid.UUID
    name: str
    level: str | None
    years_experience: float | None
    is_primary: bool


class Completeness(BaseModel):
    score: int
    missing: list[str]


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    location: str | None
    headline: str | None
    summary: str | None
    total_experience_years: float | None
    preferred_roles: list[str]
    preferred_locations: list[str]
    work_arrangement: str
    salary_currency: str
    salary_min: int | None
    salary_max: int | None
    notice_period_days: int | None
    excluded_companies: list[str]
    target_experience_min: int | None
    target_experience_max: int | None
    search_keywords: list[str]
    refresh_interval_hours: int
    education: list[EducationItem]
    certifications: list[CertificationItem]
    links: dict[str, str]
    employment: list[EmploymentOut]
    skills: list[SkillOut]
    completeness: Completeness

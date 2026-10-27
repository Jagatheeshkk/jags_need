from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.scoring import DEFAULT_SCORE_WEIGHTS

Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PortalPermission(BaseModel):
    enabled: bool = True
    auto_apply: bool = False


class AutomationRulesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    global_pause: bool = True
    min_match_score: int = Field(default=75, ge=0, le=100)
    allowed_titles: list[Item] = Field(default_factory=list, max_length=50)
    allowed_locations: list[Item] = Field(default_factory=list, max_length=50)
    min_salary: int | None = Field(default=None, ge=0)
    company_allowlist: list[Item] = Field(default_factory=list, max_length=200)
    company_blocklist: list[Item] = Field(default_factory=list, max_length=200)
    max_applications_per_day: int = Field(default=5, ge=0, le=50)
    portal_permissions: dict[str, PortalPermission] = Field(default_factory=dict)
    preferred_resume_by_role: dict[str, str] = Field(default_factory=dict)
    score_weights: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_SCORE_WEIGHTS))

    @field_validator("score_weights")
    @classmethod
    def _weights(cls, v: dict[str, int]) -> dict[str, int]:
        if set(v) != set(DEFAULT_SCORE_WEIGHTS):
            raise ValueError(f"score_weights must have exactly: {sorted(DEFAULT_SCORE_WEIGHTS)}")
        if any(w < 0 for w in v.values()) or sum(v.values()) != 100:
            raise ValueError("score_weights must be non-negative and sum to 100")
        return v


class AutomationRulesOut(AutomationRulesIn):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime | None = None


class ReadinessCheck(BaseModel):
    name: str
    status: Literal["ok", "warn", "fail", "info"]
    detail: str


class ReadinessReport(BaseModel):
    ready: bool
    paid_dependencies: list[str]
    checks: list[ReadinessCheck]

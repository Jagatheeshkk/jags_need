"""Common interface every job-portal connector implements.

A connector must never report success for an operation that did not actually succeed.
Unsupported operations raise ConnectorNotSupported so callers fall back to a manual workflow.
"""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.connectors.policies import PortalPolicy


class IntegrationMode(StrEnum):
    MOCK = "mock"  # synthetic data, local only
    UNVERIFIED = "unverified"  # permitted integration options not yet verified -> nothing automated
    MANUAL = "manual"  # verified: only manual / link-out workflows are permitted
    API = "api"  # verified, authorised API integration


class Capabilities(BaseModel):
    mode: IntegrationMode
    search_jobs: bool = False
    get_job_details: bool = False
    get_profile: bool = False
    update_profile: bool = False
    prepare_application: bool = False
    submit_application: bool = False
    get_application_status: bool = False
    notes: str = ""
    # Phase 5: what the user can still do by hand, and the evidence behind the decision.
    manual_workflows: list[str] = Field(default_factory=list)
    verification: str | None = None
    verified_on: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class JobFilters(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=20)
    titles: list[str] = Field(default_factory=list, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=20)
    work_arrangement: Literal["remote", "hybrid", "onsite", "any"] = "any"
    limit: int = Field(default=25, ge=1, le=100)


class PortalJob(BaseModel):
    external_id: str
    title: str
    company: str
    location: str | None = None
    work_arrangement: str | None = None
    description: str | None = None
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    experience_min: int | None = None
    experience_max: int | None = None
    url: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    is_synthetic: bool = False


OperationStatus = Literal["succeeded", "failed", "needs_user_action", "unknown"]


class OperationResult(BaseModel):
    status: OperationStatus
    message: str
    # True when nothing happened on any real portal (mock connector).
    simulated: bool = False
    reference: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ConnectorNotSupported(Exception):
    def __init__(self, portal: str, operation: str) -> None:
        super().__init__(f"{portal}: '{operation}' is not supported by this integration")
        self.portal = portal
        self.operation = operation


class PortalConnector(ABC):
    code: str
    name: str
    base_url: str | None = None

    @abstractmethod
    def get_capabilities(self) -> Capabilities: ...

    @abstractmethod
    def search_jobs(self, filters: JobFilters) -> list[PortalJob]: ...

    @abstractmethod
    def get_job_details(self, job_id: str) -> PortalJob: ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]: ...

    @abstractmethod
    def update_profile(self, profile: dict[str, Any]) -> OperationResult: ...

    @abstractmethod
    def prepare_application(self, job_id: str, resume_id: str) -> OperationResult: ...

    @abstractmethod
    def submit_application(self, application_id: str) -> OperationResult: ...

    @abstractmethod
    def get_application_status(self, application_id: str) -> OperationResult: ...


class UnverifiedPortalConnector(PortalConnector):
    """Placeholder for a real portal until its permitted integration options are verified (Phase 5).

    Every operation is refused. The UI shows the portal as 'Unsupported' and offers manual steps.
    """

    def __init__(self, code: str, name: str, base_url: str) -> None:
        self.code = code
        self.name = name
        self.base_url = base_url

    def get_capabilities(self) -> Capabilities:
        return Capabilities(
            mode=IntegrationMode.UNVERIFIED,
            notes=(
                "Official integration options and terms have not been verified yet (Phase 5). "
                "No automated access is attempted. Search and apply manually on the portal; "
                "the app can still track those applications."
            ),
        )

    def _refuse(self, operation: str) -> ConnectorNotSupported:
        return ConnectorNotSupported(self.code, operation)

    def search_jobs(self, filters: JobFilters) -> list[PortalJob]:
        raise self._refuse("search_jobs")

    def get_job_details(self, job_id: str) -> PortalJob:
        raise self._refuse("get_job_details")

    def get_profile(self) -> dict[str, Any]:
        raise self._refuse("get_profile")

    def update_profile(self, profile: dict[str, Any]) -> OperationResult:
        raise self._refuse("update_profile")

    def prepare_application(self, job_id: str, resume_id: str) -> OperationResult:
        raise self._refuse("prepare_application")

    def submit_application(self, application_id: str) -> OperationResult:
        raise self._refuse("submit_application")

    def get_application_status(self, application_id: str) -> OperationResult:
        raise self._refuse("get_application_status")


class ManualPortalConnector(UnverifiedPortalConnector):
    """A real portal whose terms do not permit automated access (verified in Phase 5).

    Every automated operation is refused. The app offers manual workflows instead: a link that
    opens the portal's own search in the user's browser, and capture of listings the user pastes.
    The portal is never contacted by the server.
    """

    def __init__(self, policy: "PortalPolicy") -> None:
        super().__init__(policy.code, policy.name, policy.base_url)
        self.policy = policy

    def get_capabilities(self) -> Capabilities:
        from app.connectors.policies import MANUAL_WORKFLOWS, VERIFIED_ON

        return Capabilities(
            mode=IntegrationMode.MANUAL,
            notes=self.policy.summary,
            manual_workflows=list(MANUAL_WORKFLOWS),
            verification=self.policy.verification,
            verified_on=VERIFIED_ON,
            evidence=[{"url": e.url, "finding": e.finding, "retrieved": e.retrieved} for e in self.policy.evidence],
        )

    def owns_url(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return urlsplit(url).scheme == "https" and any(host == d or host.endswith("." + d) for d in self.policy.domains)

    def search_url(self, keywords: str, location: str | None = None) -> str:
        """The portal's own search page, opened in the user's browser (the server never requests it)."""
        kw, loc = keywords.strip(), (location or "").strip()
        if self.code == "linkedin":
            return f"https://www.linkedin.com/jobs/search/?{urlencode({'keywords': kw, 'location': loc})}"
        if self.code == "indeed":
            return f"https://in.indeed.com/jobs?{urlencode({'q': kw, 'l': loc})}"
        if self.code == "naukri":
            slug = re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-") or "qa"
            city = re.sub(r"[^a-z0-9]+", "-", loc.lower()).strip("-")
            return f"https://www.naukri.com/{slug}-jobs" + (f"-in-{city}" if city else "")
        if self.code == "cutshort":
            return "https://cutshort.io/jobs"
        return self.policy.base_url  # no documented search URL: open the site

"""Mock portal connector backed by a synthetic fixture.

All jobs are fictitious and flagged is_synthetic. All write operations are simulated and
say so in their result; nothing is ever sent to a real portal.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.connectors.base import (
    Capabilities,
    IntegrationMode,
    JobFilters,
    OperationResult,
    PortalConnector,
    PortalJob,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_jobs.json"


@lru_cache
def _load_fixture() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _to_job(raw: dict[str, Any]) -> PortalJob:
    # Dates are relative to today so freshness indicators behave like a live feed.
    today = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    posted = today - timedelta(days=int(raw.get("posted_days_ago", 0)))
    expires = today - timedelta(days=int(raw["expires_days_ago"])) if "expires_days_ago" in raw else None
    return PortalJob(
        external_id=raw["id"],
        title=raw["title"],
        company=raw["company"],
        location=raw.get("location"),
        work_arrangement=raw.get("work_arrangement"),
        description=raw.get("description"),
        skills=raw.get("skills", []),
        salary_min=raw.get("salary_min"),
        salary_max=raw.get("salary_max"),
        salary_currency=raw.get("salary_currency"),
        experience_min=raw.get("experience_min"),
        experience_max=raw.get("experience_max"),
        url=f"https://mock-portal.invalid/jobs/{raw['id']}",
        posted_at=posted,
        expires_at=expires,
        is_synthetic=True,
    )


class MockConnector(PortalConnector):
    code = "mock"
    name = "Mock Portal (synthetic data)"
    base_url = "https://mock-portal.invalid"

    def __init__(self) -> None:
        self._profile: dict[str, Any] = {}

    def get_capabilities(self) -> Capabilities:
        return Capabilities(
            mode=IntegrationMode.MOCK,
            search_jobs=True,
            get_job_details=True,
            get_profile=True,
            update_profile=True,
            prepare_application=True,
            submit_application=True,
            get_application_status=True,
            notes="Synthetic jobs for development and tests. Submissions are simulated.",
        )

    def search_jobs(self, filters: JobFilters) -> list[PortalJob]:
        jobs = [_to_job(r) for r in _load_fixture()]
        terms = [t.lower() for t in filters.titles + filters.keywords if t.strip()]
        locations = [loc.lower() for loc in filters.locations if loc.strip()]

        def keep(job: PortalJob) -> bool:
            haystack = " ".join([job.title, job.description or "", " ".join(job.skills)]).lower()
            if terms and not any(t in haystack for t in terms):
                return False
            if filters.work_arrangement != "any" and job.work_arrangement != filters.work_arrangement:
                return False
            if locations:
                loc = (job.location or "").lower()
                remote_ok = job.work_arrangement == "remote" and "remote" in locations
                if not remote_ok and not any(x in loc for x in locations):
                    return False
            return True

        return [j for j in jobs if keep(j)][: filters.limit]

    def get_job_details(self, job_id: str) -> PortalJob:
        for raw in _load_fixture():
            if raw["id"] == job_id:
                return _to_job(raw)
        raise KeyError(job_id)

    def get_profile(self) -> dict[str, Any]:
        return dict(self._profile)

    def update_profile(self, profile: dict[str, Any]) -> OperationResult:
        self._profile = dict(profile)
        return OperationResult(status="succeeded", simulated=True, message="Simulated: mock profile updated locally.")

    def prepare_application(self, job_id: str, resume_id: str) -> OperationResult:
        self.get_job_details(job_id)
        return OperationResult(
            status="succeeded",
            simulated=True,
            message="Simulated: application prepared.",
            data={"job_id": job_id, "resume_id": resume_id, "questions": []},
        )

    def submit_application(self, application_id: str) -> OperationResult:
        ref = "MOCK-" + hashlib.sha256(application_id.encode()).hexdigest()[:10].upper()
        return OperationResult(
            status="succeeded",
            simulated=True,
            reference=ref,
            message="Simulated submission. No application was sent to any real portal.",
        )

    def get_application_status(self, application_id: str) -> OperationResult:
        return OperationResult(status="succeeded", simulated=True, message="Simulated status: received.")

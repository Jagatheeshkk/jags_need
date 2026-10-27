"""Verified integration policy for each real portal (Phase 5).

Every conclusion here comes from the portal's own published terms or developer documentation,
checked on VERIFIED_ON. Summaries are paraphrased; follow the URLs for the authoritative text.
Re-check these sources before changing any capability: terms change.
"""

from dataclasses import dataclass, field
from typing import Literal

VERIFIED_ON = "2026-10-28"

# terms_reviewed     - official terms/docs were read and they rule out automated access
# terms_unavailable  - the official terms could not be retrieved; treated as not permitted
Verification = Literal["terms_reviewed", "terms_unavailable"]

# Manual workflows the app offers for every real portal. None of them access the portal
# automatically: the user's own browser opens the portal, and data comes from the user.
MANUAL_WORKFLOWS = [
    "search_link",  # opens the portal's own job search in your browser
    "manual_job_capture",  # you paste a listing's details; the app never fetches the page
    "profile_content",  # portal-ready profile text you copy across yourself
    "manual_application_tracking",  # you apply on the portal, then confirm it in the tracker
]


@dataclass(frozen=True)
class Evidence:
    url: str
    finding: str
    retrieved: bool = True


@dataclass(frozen=True)
class PortalPolicy:
    code: str
    name: str
    base_url: str
    domains: tuple[str, ...]
    verification: Verification
    summary: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


POLICIES: dict[str, PortalPolicy] = {
    "linkedin": PortalPolicy(
        code="linkedin",
        name="LinkedIn",
        base_url="https://www.linkedin.com",
        domains=("linkedin.com",),
        verification="terms_reviewed",
        summary=(
            "The User Agreement forbids scrapers, bots and other unauthorised automated access, and LinkedIn's "
            "Talent APIs are for ATS partners and recruiter customers, not individual job seekers. "
            "Manual workflows only."
        ),
        evidence=(
            Evidence(
                "https://www.linkedin.com/legal/user-agreement",
                "User Agreement (effective 3 Nov 2025), section 8.2: no software, scripts, robots or "
                "crawlers to scrape or copy the Services; no bots or unauthorised automated access.",
            ),
            Evidence(
                "https://www.linkedin.com/help/linkedin/answer/a1341387",
                "Help page 'Prohibited software and extensions': third-party tools that scrape or automate "
                "activity are not allowed; no exception for job seekers.",
            ),
            Evidence(
                "https://learn.microsoft.com/en-us/linkedin/talent/",
                "Talent Solutions APIs (Apply Connect, Apply with LinkedIn, Job Posting) serve ATS "
                "integrations and recruiter customers; no job-seeker API.",
            ),
        ),
    ),
    "indeed": PortalPolicy(
        code="indeed",
        name="Indeed",
        base_url="https://in.indeed.com",
        domains=("indeed.com",),
        verification="terms_reviewed",
        summary=(
            "Job seekers may use Indeed for personal, non-commercial job search; automating Indeed Apply with "
            "scripts or bots is not allowed, and Indeed's APIs are for employers and integration developers. "
            "Manual workflows only."
        ),
        evidence=(
            Evidence(
                "https://www.indeed.com/legal",
                "Terms (updated 29 Sep 2026): job-seeker licence is personal and non-commercial; "
                "automation, scripting or bots for Indeed Apply not allowed outside official vendors.",
            ),
            Evidence(
                "https://www.indeed.com/legal",
                "API terms address developers building integrations for employers/end users and the "
                "Sponsored Jobs API for advertisers; job seekers are not named as API users.",
            ),
        ),
    ),
    "naukri": PortalPolicy(
        code="naukri",
        name="Naukri",
        base_url="https://www.naukri.com",
        domains=("naukri.com",),
        verification="terms_unavailable",
        summary=(
            "Naukri's terms and robots.txt refused automated retrieval (HTTP 403), and no public job-seeker API "
            "was found. Without verified permission nothing is automated. Manual workflows only."
        ),
        evidence=(
            Evidence(
                "https://www.naukri.com/termsconditions",
                "Could not be retrieved (HTTP 403 to an automated request). Read it in your browser.",
                retrieved=False,
            ),
            Evidence(
                "https://www.naukri.com/robots.txt",
                "Could not be retrieved (HTTP 403 to an automated request).",
                retrieved=False,
            ),
        ),
    ),
    "instahyre": PortalPolicy(
        code="instahyre",
        name="Instahyre",
        base_url="https://www.instahyre.com",
        domains=("instahyre.com",),
        verification="terms_unavailable",
        summary=(
            "Instahyre's terms refused automated retrieval (HTTP 403) and no public job-seeker API was found. "
            "Without verified permission nothing is automated. Manual workflows only."
        ),
        evidence=(
            Evidence(
                "https://www.instahyre.com/terms/",
                "Could not be retrieved (HTTP 403 to an automated request). Read it in your browser.",
                retrieved=False,
            ),
        ),
    ),
    "cutshort": PortalPolicy(
        code="cutshort",
        name="Cutshort",
        base_url="https://cutshort.io",
        domains=("cutshort.io",),
        verification="terms_reviewed",
        summary=(
            "Cutshort's terms forbid automated processes to access the service and scraping; its API is "
            "discretionary and for customers' own hiring. Manual workflows only."
        ),
        evidence=(
            Evidence(
                "https://cutshort.io/terms",
                "Terms (updated 7 Sep 2026), section 7: no automated process or service to access the "
                "Service; no scraping or systematic data collection.",
            ),
            Evidence(
                "https://cutshort.io/terms",
                "Section 6: API/MCP access is at Cutshort's discretion, for the customer's own hiring; "
                "section 5: Freedom Plans are for manual use of the website.",
            ),
        ),
    ),
}

# Portal integrations (Phase 5)

**Verified:** 2026-10-28, from each portal's own terms and developer documentation.
**Result:** none of the five portals permits automated access for an individual job seeker,
so every real portal is **manual workflows only**. The server never contacts any portal.

The same facts are stored in `services/api/app/connectors/policies.py` and shown on the
**Portal Connections** page, so the app and this document cannot drift apart silently.
Findings below are paraphrased; follow the links for the authoritative wording.

| Portal | Verification | Official job-seeker API | Automated access in the terms | Decision |
|---|---|---|---|---|
| LinkedIn | Terms reviewed | No. Talent Solutions APIs (Apply Connect, Apply with LinkedIn, Job Posting) are for ATS partners and recruiter customers | Forbidden: scrapers, crawlers, bots and other unauthorised automated access (User Agreement 8.2); help page confirms, no job-seeker exception | Manual only |
| Indeed | Terms reviewed | No. API terms address integration developers for employers and the Sponsored Jobs API for advertisers | Job-seeker licence is personal and non-commercial; automating Indeed Apply with scripts or bots is not allowed outside official vendors | Manual only |
| Naukri | Terms **not retrievable** (HTTP 403 to automated requests for the terms page and robots.txt) | None found | Not verified | Manual only (no verified permission) |
| Instahyre | Terms **not retrievable** (HTTP 403) | None found | Not verified | Manual only (no verified permission) |
| Cutshort | Terms reviewed | API/MCP access is discretionary and for the customer's own hiring | Forbidden: automated processes to access the service, scraping and systematic data collection (section 7); Freedom Plans are for manual use | Manual only |

### Sources

| Portal | Source | Note |
|---|---|---|
| LinkedIn | https://www.linkedin.com/legal/user-agreement | Effective 3 Nov 2025, section 8.2 |
| LinkedIn | https://www.linkedin.com/help/linkedin/answer/a1341387 | "Prohibited software and extensions" |
| LinkedIn | https://learn.microsoft.com/en-us/linkedin/talent/ | Talent Solutions API overview |
| Indeed | https://www.indeed.com/legal | Updated 29 Sep 2026 (job seeker, API and Indeed Apply terms) |
| Naukri | https://www.naukri.com/termsconditions | Refused automated retrieval; read it in your browser |
| Instahyre | https://www.instahyre.com/terms/ | Refused automated retrieval; read it in your browser |
| Cutshort | https://cutshort.io/terms | Updated 7 Sep 2026, sections 5–7 |

A third-party search summary suggested Naukri's sister site Naukrigulf forbids automated
scraping; that is not used as evidence because the primary page could not be read.

## What the app does instead

| Workflow | How | Never does |
|---|---|---|
| Search link | Builds a link to the portal's own search for your preferred role and location (`GET /api/portals/{code}/search-link`); your browser opens it | Request the page from the server |
| Manual job capture | You paste a listing (`POST /api/jobs/manual`). The link must be `https://` on that portal's domain. The listing is normalised, de-duplicated (canonical URL, then content similarity across portals) and scored like any job | Fetch, crawl or validate the link online |
| Profile text | `Profile Sync` builds each section from your profile, marks what changed since your last confirmed sync, and gives copy buttons and steps | Log in to or edit the portal |
| Applications | Rules engine routes real-portal jobs to the Approval Queue ("does not permit automated submission"); approving marks the application *prepared*; you apply on the portal and confirm in the tracker | Submit, simulate or auto-fill on a real portal |

Search URL formats for LinkedIn, Indeed and Naukri follow those portals' public search URLs;
Instahyre and Cutshort links open their jobs home page because no documented search URL format
was confirmed. If a portal changes its URLs, the link still lands on that portal.

Profile character limits are not enforced: LinkedIn's limits are widely reported (220-character
headline, 2,600-character About) but not published on an official help page, and no official
limits were found for the others. The portal's own editor enforces them; the app shows counts.

## Re-verification checklist

1. Re-read each source above. Look for a published job-seeker API or an explicit permission for
   personal automation.
2. If a portal publishes such permission, record the new evidence in `policies.py` first, then
   implement only that operation behind a capability flag, with tests using recorded responses
   (never live calls in CI).
3. Keep CAPTCHA/MFA/anti-bot bypass, credential storage and scraping out of scope regardless.

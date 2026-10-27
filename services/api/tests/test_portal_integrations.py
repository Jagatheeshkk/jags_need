"""Phase 5: verified manual-only portals, manual job capture, search links and profile sync."""

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.connectors.base import ConnectorNotSupported, JobFilters, ManualPortalConnector
from app.connectors.policies import POLICIES
from app.connectors.registry import get_connector
from app.models import Job, JobSource, ProfileSyncRun, User
from app.services import ingestion

REAL = ["linkedin", "indeed", "naukri", "instahyre", "cutshort"]

LISTING = {
    "portal": "linkedin",
    "url": "https://www.linkedin.com/jobs/view/1234567890/?trk=public_jobs&refId=abc",
    "title": "QA Lead",
    "company": "Real Example Corp",
    "location": "Bengaluru",
    "work_arrangement": "hybrid",
    "description": "Lead regression and UAT testing for an HRMS product using Playwright and Postman.",
    "skills": ["Playwright", "Postman", "UAT"],
    "experience_min": 8,
    "experience_max": 12,
}


# ---------- policies and connectors ----------


@pytest.mark.parametrize("code", REAL)
def test_every_automated_operation_is_refused(code: str) -> None:
    c = get_connector(code)
    assert isinstance(c, ManualPortalConnector)
    for call in (
        lambda: c.search_jobs(JobFilters()),
        lambda: c.get_job_details("x"),
        lambda: c.get_profile(),
        lambda: c.update_profile({}),
        lambda: c.prepare_application("x", "y"),
        lambda: c.submit_application("x"),
        lambda: c.get_application_status("x"),
    ):
        with pytest.raises(ConnectorNotSupported):
            call()


def test_policies_record_evidence() -> None:
    assert set(POLICIES) == set(REAL)
    for p in POLICIES.values():
        assert p.evidence and p.summary.endswith("Manual workflows only.")
        if p.verification == "terms_unavailable":
            assert any(not e.retrieved for e in p.evidence)


@pytest.mark.parametrize(
    "code,url,ok",
    [
        ("indeed", "https://in.indeed.com/viewjob?jk=1", True),
        ("indeed", "https://www.indeed.com/viewjob?jk=1", True),
        ("indeed", "https://evilindeed.com/viewjob", False),
        ("indeed", "https://indeed.com.evil.io/x", False),
        ("linkedin", "http://www.linkedin.com/jobs/view/1", False),  # https only
        ("naukri", "https://www.naukri.com/job-listings-qa-lead-1", True),
        ("naukri", "https://www.linkedin.com/jobs/view/1", False),  # wrong portal
        ("cutshort", "https://cutshort.io/job/QA-Lead-abc", True),
    ],
)
def test_url_must_belong_to_portal(code: str, url: str, ok: bool) -> None:
    c = get_connector(code)
    assert isinstance(c, ManualPortalConnector)
    assert c.owns_url(url) is ok


def test_search_links() -> None:
    li = get_connector("linkedin")
    assert isinstance(li, ManualPortalConnector)
    q = parse_qs(urlsplit(li.search_url("QA Lead", "Bengaluru")).query)
    assert q == {"keywords": ["QA Lead"], "location": ["Bengaluru"]}
    nk = get_connector("naukri")
    assert isinstance(nk, ManualPortalConnector)
    assert nk.search_url("QA Lead & Test", "Navi Mumbai") == "https://www.naukri.com/qa-lead-test-jobs-in-navi-mumbai"
    ih = get_connector("instahyre")
    assert isinstance(ih, ManualPortalConnector)
    assert ih.search_url("QA") == "https://www.instahyre.com"


def test_search_link_api_uses_profile(owner: TestClient) -> None:
    owner.patch("/api/profile", json={"preferred_roles": ["Test Manager"], "preferred_locations": ["Remote", "Pune"]})
    r = owner.get("/api/portals/indeed/search-link").json()
    assert r["keywords"] == "Test Manager" and r["location"] == "Pune"
    assert r["url"] == "https://in.indeed.com/jobs?q=Test+Manager&l=Pune"
    assert owner.get("/api/portals/mock/search-link").status_code == 404


def test_refresh_never_touches_real_portals(owner: TestClient) -> None:
    owner.patch("/api/profile", json={"preferred_roles": ["QA Lead"]})
    res = owner.post("/api/jobs/refresh").json()["result"]
    assert res["portals_searched"] == ["mock"]
    assert set(res["portals_skipped"]) == set(REAL)
    assert all("manual portal" in v for v in res["portals_skipped"].values())


# ---------- manual job capture ----------


def test_capture_real_listing_is_scored_and_deduplicated(owner: TestClient, db_factory) -> None:
    owner.patch("/api/profile", json={"preferred_roles": ["QA Lead"], "total_experience_years": 10})
    owner.put("/api/profile/skills", json=[{"name": "Playwright"}, {"name": "Postman"}])
    r = owner.post("/api/jobs/manual", json=LISTING)
    assert r.status_code == 201 and r.json()["outcome"] == "created"
    job_id = r.json()["job_id"]
    detail = owner.get(f"/api/jobs/{job_id}").json()
    assert detail["is_synthetic"] is False
    assert detail["sources"][0]["portal"] == "linkedin"
    assert detail["canonical_url"] == "https://linkedin.com/jobs/view/1234567890"  # tracking params dropped
    assert detail["match"]["score"] > 0 and "Playwright" in detail["match"]["matched_skills"]
    assert owner.get("/api/overview").json()["jobs"]["real"] == 1

    # Same link pasted again (different tracking params): updated, not duplicated.
    again = owner.post(
        "/api/jobs/manual", json={**LISTING, "url": "https://linkedin.com/jobs/view/1234567890?utm_source=x"}
    )
    assert again.status_code == 200 and again.json()["outcome"] == "updated"
    # Same listing found on Indeed: merged into the same job as a second source.
    other = owner.post(
        "/api/jobs/manual", json={**LISTING, "portal": "indeed", "url": "https://in.indeed.com/viewjob?jk=abc123"}
    )
    assert other.json()["outcome"] == "merged" and other.json()["job_id"] == job_id
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.scalar(select(func.count()).select_from(JobSource)) == 2


@pytest.mark.parametrize(
    "change,status_code",
    [
        ({"url": "https://evil.example.com/jobs/1"}, 422),
        ({"url": "http://www.linkedin.com/jobs/view/1"}, 422),
        ({"portal": "mock"}, 422),
        ({"title": ""}, 422),
        ({"description": "x" * 20001}, 422),
        ({"unknown": 1}, 422),
    ],
)
def test_capture_validation(owner: TestClient, change: dict, status_code: int) -> None:
    assert owner.post("/api/jobs/manual", json={**LISTING, **change}).status_code == status_code


def test_capture_never_fetches_the_url(owner: TestClient, monkeypatch) -> None:
    import socket

    def boom(*args, **kwargs):  # any network access from the server would fail the test
        raise AssertionError("server attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    assert owner.post("/api/jobs/manual", json=LISTING).status_code == 201


def test_manual_portal_jobs_go_to_approval_not_submission(owner: TestClient) -> None:
    owner.patch("/api/profile", json={"full_name": "Asha Example", "total_experience_years": 10})
    owner.post("/api/jobs/manual", json=LISTING)
    rules = owner.get("/api/settings/automation").json()
    rules.pop("updated_at")
    rules.update(
        enabled=True,
        global_pause=False,
        min_match_score=0,
        portal_permissions={"linkedin": {"enabled": True, "auto_apply": True}},
    )
    assert owner.put("/api/settings/automation", json=rules).status_code == 200
    d = next(x for x in owner.get("/api/automation/preview").json()["decisions"] if x["company"] == "Real Example Corp")
    assert d["action"] == "approval"
    assert any("does not permit automated submission" in r for r in d["reasons"])
    owner.post("/api/automation/run")
    req = next(r for r in owner.get("/api/approvals?status=pending").json() if r["payload"]["portal"] == "linkedin")
    out = owner.post(f"/api/approvals/{req['id']}/approve", json={"confirm_reviewed": True}).json()
    assert "Apply on the portal yourself" in out["outcome"]
    app = owner.get(f"/api/applications/{req['subject_id']}").json()
    assert app["status"] == "prepared" and app["is_simulated"] is False and app["submitted_at"] is None
    assert owner.post(f"/api/applications/{app['id']}/simulate-submit").status_code == 409  # real job: never simulated


# ---------- profile sync ----------


@pytest.fixture
def synced_profile(owner: TestClient) -> TestClient:
    owner.patch(
        "/api/profile",
        json={
            "full_name": "Asha Example",
            "headline": "QA Lead",
            "summary": "QA lead with HRMS testing experience.",
            "preferred_roles": ["QA Lead"],
            "notice_period_days": 60,
            "education": [{"institution": "Example University", "degree": "B.E.", "end_year": 2012}],
        },
    )
    owner.put("/api/profile/skills", json=[{"name": "Playwright", "is_primary": True}, {"name": "Postman"}])
    owner.post(
        "/api/profile/employment",
        json={
            "company": "Example HR Cloud",
            "title": "QA Lead",
            "start_date": "2016-01-01",
            "is_current": True,
            "achievements": ["Cut regression time by 40%"],
        },
    )
    return owner


def test_profile_sync_manual_flow(synced_profile: TestClient, db_factory) -> None:
    c = synced_profile
    p = c.get("/api/profile-sync/naukri/preview").json()
    assert p["automated"] is False and p["last_synced_at"] is None
    fields = {f["key"]: f for f in p["fields"]}
    assert fields["skills"]["value"] == "Playwright, Postman"
    assert "QA Lead — Example HR Cloud" in fields["experience"]["value"]
    assert "• Cut regression time by 40%" in fields["experience"]["value"]
    assert fields["headline"]["chars"] == len("QA Lead")
    assert set(p["changed"]) == set(fields)  # first sync: everything is new
    assert "naukri.com" in p["instructions"][0]

    run = c.post("/api/profile-sync/naukri/prepare")
    assert run.status_code == 201 and run.json()["status"] == "manual_required"
    rid = run.json()["id"]
    assert c.post("/api/profile-sync/naukri/prepare").json()["id"] == rid  # idempotent
    assert c.post(f"/api/profile-sync/runs/{rid}/run").status_code == 409  # no automated update for Naukri
    assert c.post(f"/api/profile-sync/runs/{rid}/confirm", json={}).status_code == 400
    done = c.post(f"/api/profile-sync/runs/{rid}/confirm", json={"confirm_updated": True}).json()
    assert done["status"] == "manual_completed"
    assert done["result"] == {"confirmed_by_user": True, "automated": False, "fields": p["changed"]}

    # After a profile change, only that section shows as changed.
    c.patch("/api/profile", json={"headline": "QA Lead | HRMS"})
    p2 = c.get("/api/profile-sync/naukri/preview").json()
    assert p2["changed"] == ["headline"] and p2["last_synced_at"]
    # Other portals are tracked separately.
    assert len(c.get("/api/profile-sync/linkedin/preview").json()["changed"]) == 7
    hist = c.get("/api/profile-sync/runs?portal=naukri").json()
    assert [h["status"] for h in hist] == ["manual_completed"]
    assert c.get("/api/data/export").json()["profile_sync_runs"][0]["status"] == "manual_completed"


def test_profile_sync_mock_is_simulated(synced_profile: TestClient) -> None:
    c = synced_profile
    assert c.get("/api/profile-sync/mock/preview").json()["automated"] is True
    run = c.post("/api/profile-sync/mock/prepare").json()
    assert run["status"] == "pending"
    done = c.post(f"/api/profile-sync/runs/{run['id']}/run").json()
    assert done["status"] == "succeeded" and done["result"]["simulated"] is True


def test_profile_sync_cancel_and_errors(synced_profile: TestClient) -> None:
    c = synced_profile
    rid = c.post("/api/profile-sync/cutshort/prepare").json()["id"]
    assert c.post(f"/api/profile-sync/runs/{rid}/cancel").json()["status"] == "cancelled"
    assert c.post(f"/api/profile-sync/runs/{rid}/confirm", json={"confirm_updated": True}).status_code == 409
    assert c.get("/api/profile-sync/monster/preview").status_code == 404
    assert c.post("/api/profile-sync/runs/00000000-0000-0000-0000-000000000000/cancel").status_code == 404


def test_sync_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/profile-sync/runs").status_code == 401
    assert client.post("/api/jobs/manual", json=LISTING).status_code == 401
    assert client.get("/api/portals/linkedin/search-link").status_code == 401


def test_refresh_with_real_jobs_keeps_them(owner: TestClient, db_factory) -> None:
    owner.post("/api/jobs/manual", json=LISTING)
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        ingestion.run_refresh(db, user, filters=JobFilters(limit=100))
        real = db.scalar(select(func.count()).select_from(Job).where(Job.is_synthetic.is_(False)))
        runs = db.scalar(select(func.count()).select_from(ProfileSyncRun))
    assert real == 1 and runs == 0

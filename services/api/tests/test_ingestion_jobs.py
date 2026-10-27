from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.connectors.base import Capabilities, IntegrationMode, JobFilters, PortalJob
from app.connectors.mock import MockConnector
from app.models import Job, JobMatch, JobSource, Notification, TaskRun, User
from app.services import ingestion, tasks

PROFILE = {
    "preferred_roles": ["QA Lead", "Test Manager"],
    "preferred_locations": ["Bengaluru"],
    "work_arrangement": "any",
    "salary_min": 2_000_000,
    "total_experience_years": 10,
    "summary": "QA lead with HRMS and ERP testing experience across regression and UAT cycles.",
}
SKILLS = [{"name": n} for n in ["Playwright", "Postman", "Functional Testing", "Regression Testing", "UAT", "HRMS"]]


def setup_profile(c: TestClient) -> None:
    assert c.patch("/api/profile", json=PROFILE).status_code == 200
    assert c.put("/api/profile/skills", json=SKILLS).status_code == 200


def count(db_factory, model) -> int:
    with db_factory() as db:
        return int(db.scalar(select(func.count()).select_from(model)))


class FlakyConnector(MockConnector):
    code = "flaky"

    def search_jobs(self, filters: JobFilters) -> list[PortalJob]:
        raise RuntimeError("simulated portal outage")


class FeedConnector(MockConnector):
    """Second synthetic feed re-publishing a mock listing under its own id (cross-source duplicate)."""

    code = "feed"

    def get_capabilities(self) -> Capabilities:
        return Capabilities(mode=IntegrationMode.MOCK, search_jobs=True)

    def search_jobs(self, filters: JobFilters) -> list[PortalJob]:
        job = MockConnector().get_job_details("MOCK-1003")
        return [job.model_copy(update={"external_id": "FEED-9", "url": job.url + "?utm_source=feed"})]


# ---------- refresh + dedup through the API ----------


def test_refresh_ingests_dedups_and_scores(owner: TestClient, db_factory) -> None:
    setup_profile(owner)
    r = owner.post("/api/jobs/refresh")
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "succeeded"
    res = run["result"]
    assert res["portals_searched"] == ["mock"]
    assert set(res["portals_skipped"]) == {"naukri", "linkedin", "indeed", "instahyre", "cutshort"}
    assert res["merged"] == 1  # MOCK-1011 is a repost of MOCK-1001
    created = res["created"]
    assert count(db_factory, Job) == created
    assert count(db_factory, JobMatch) == created
    assert count(db_factory, Notification) == 2  # welcome + "new jobs found"

    again = owner.post("/api/jobs/refresh").json()["result"]
    assert again["created"] == 0 and again["updated"] + again["merged"] == res["created"] + res["merged"]
    assert count(db_factory, Job) == created  # idempotent
    assert count(db_factory, Notification) == 2  # no notification without new jobs


def test_repost_has_two_sources(owner: TestClient, db_factory) -> None:
    setup_profile(owner)
    owner.post("/api/jobs/refresh")
    with db_factory() as db:
        job = db.scalars(
            select(Job).where(Job.title == "QA Lead", Job.company_key == "example hr cloud synthetic")
        ).one()
    detail = owner.get(f"/api/jobs/{job.id}").json()
    assert detail["source_count"] == 2
    assert {s["external_id"] for s in detail["sources"]} == {"MOCK-1001", "MOCK-1011"}


def test_cross_source_duplicate_by_canonical_url(owner: TestClient, db_factory) -> None:
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        ingestion.run_refresh(db, user, connectors=[MockConnector()], filters=JobFilters(limit=100))
        before = db.scalar(select(func.count()).select_from(Job))
        from app.models import Portal

        db.add(Portal(code="feed", name="Feed", integration_mode="mock"))
        db.commit()
        run = ingestion.run_refresh(db, user, connectors=[FeedConnector()], filters=JobFilters())
    assert run.result["merged"] == 1 and run.result["created"] == 0
    assert count(db_factory, Job) == before
    assert count(db_factory, JobSource) == before + 2  # repost + feed copy


def test_one_failing_portal_does_not_stop_others(owner: TestClient, db_factory) -> None:
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        from app.models import Portal

        db.add(Portal(code="flaky", name="Flaky", integration_mode="mock"))
        db.commit()
        run = ingestion.run_refresh(db, user, connectors=[FlakyConnector(), MockConnector()], filters=JobFilters())
    assert run.status == "succeeded"
    assert "simulated portal outage" in run.result["portal_errors"]["flaky"]
    assert run.result["created"] > 0


def test_expired_listing_marked_and_hidden_by_default(owner: TestClient) -> None:
    setup_profile(owner)
    res = owner.post("/api/jobs/refresh").json()["result"]
    assert res["expired"] == 1
    titles = [j["title"] for j in owner.get("/api/jobs").json()["items"]]
    assert "QA Lead - Payroll Platform" not in titles
    all_titles = [j["title"] for j in owner.get("/api/jobs?include_expired=true").json()["items"]]
    assert "QA Lead - Payroll Platform" in all_titles


# ---------- task state / recovery ----------


def test_concurrent_refresh_rejected_and_stale_run_recovered(owner: TestClient, db_factory) -> None:
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        stuck = tasks.start(db, user.id, ingestion.KIND)
    assert owner.post("/api/jobs/refresh").status_code == 409

    with db_factory() as db:
        run = db.get(TaskRun, stuck.id)
        run.heartbeat_at = datetime.now(UTC) - timedelta(minutes=30)  # instance slept mid-run
        db.commit()
    r = owner.post("/api/jobs/refresh")
    assert r.status_code == 200 and r.json()["status"] == "succeeded"
    runs = {x["id"]: x for x in owner.get("/api/jobs/runs").json()}
    assert runs[str(stuck.id)]["status"] == "interrupted"
    assert "Safe to retry" in runs[str(stuck.id)]["error"]


def test_idempotency_key_replays_finished_run(owner: TestClient, db_factory) -> None:
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        first = tasks.start(db, user.id, "demo", key="demo-key")
        tasks.finish(db, first, {"n": 1})
        again = tasks.start(db, user.id, "demo", key="demo-key")
    assert again.id == first.id and again.status == "succeeded"


def test_only_if_due_respects_interval(owner: TestClient) -> None:
    setup_profile(owner)
    first = owner.post("/api/jobs/refresh?only_if_due=true").json()
    assert first["trigger"] == "scheduled"
    second = owner.post("/api/jobs/refresh?only_if_due=true").json()
    assert second["id"] == first["id"]  # not due yet: returns last run, no new work
    assert owner.get("/api/jobs").json()["refresh_due"] is False


# ---------- listing, filters, save, feedback, digest ----------


@pytest.fixture
def stocked(owner: TestClient, db_factory) -> TestClient:
    """Profile set up and the whole mock feed ingested (refresh normally searches by profile roles)."""
    setup_profile(owner)
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        ingestion.run_refresh(db, user, filters=JobFilters(limit=100))
    return owner


def test_refresh_searches_with_profile_roles_and_locations(owner: TestClient) -> None:
    setup_profile(owner)
    owner.post("/api/jobs/refresh")
    titles = {j["title"] for j in owner.get("/api/jobs").json()["items"]}
    assert "QA Lead" in titles
    assert "Data Engineer" not in titles  # does not match the preferred roles
    assert "Test Manager" not in titles  # Pune is outside the preferred locations


def test_list_sorted_by_score_with_explanations(stocked: TestClient) -> None:
    data = stocked.get("/api/jobs").json()
    scores = [j["match"]["score"] for j in data["items"]]
    assert scores == sorted(scores, reverse=True)
    assert all(j["is_synthetic"] for j in data["items"])
    top = data["items"][0]
    assert top["match"]["score"] > 60 and top["freshness"] in {"new", "fresh"}
    detail = stocked.get(f"/api/jobs/{top['id']}").json()
    assert "Matched skills" in detail["explanation"]
    assert set(detail["match"]["components"]) == {
        "skills_experience",
        "role_responsibilities",
        "domain_experience",
        "location_work_arrangement",
        "compensation_fit",
    }
    bottom = {j["title"]: j["match"]["score"] for j in data["items"][-2:]}
    assert set(bottom) == {"Data Engineer", "Junior Software Tester"}
    assert bottom["Data Engineer"] <= 30  # outside QA: capped


def test_filters(stocked: TestClient) -> None:
    def titles(qs: str) -> set[str]:
        return {j["title"] for j in stocked.get(f"/api/jobs?{qs}").json()["items"]}

    assert titles("work_arrangement=remote") == {"Senior QA Engineer", "Software Quality Engineering Lead"}
    assert "Data Engineer" not in titles("min_score=50")
    assert titles("role=manager") == {"Test Manager", "QA Manager"}
    assert "Junior Software Tester" not in titles("min_salary=1000000")
    assert "Functional Test Lead" in titles("min_salary=99000000")  # unknown salary is kept
    assert titles("include_synthetic=false") == set()
    assert "QA Manager" not in titles("eligible_only=true")  # needs 12+ years, profile has 10
    assert "QA Manager" in titles("")
    assert titles("location=pune") == {"Test Manager"}


def test_save_feedback_and_saved_filter(stocked: TestClient) -> None:
    job = stocked.get("/api/jobs").json()["items"][0]
    assert stocked.put(f"/api/jobs/{job['id']}/saved", json={"saved": True}).json()["is_saved"] is True
    assert (
        stocked.put(f"/api/jobs/{job['id']}/feedback", json={"feedback": "good_match"}).json()["feedback"]
        == "good_match"
    )
    saved = stocked.get("/api/jobs?saved_only=true").json()["items"]
    assert [j["id"] for j in saved] == [job["id"]]
    # saving survives rescoring after a profile change
    stocked.patch("/api/profile", json={"salary_min": 9_000_000})
    again = stocked.get("/api/jobs?saved_only=true").json()["items"][0]
    assert again["match"]["is_saved"] and again["match"]["feedback"] == "good_match"
    assert stocked.put(f"/api/jobs/{job['id']}/feedback", json={"feedback": "meh"}).status_code == 422
    assert stocked.get("/api/overview").json()["saved_jobs"] == 1


def test_profile_change_rescores(stocked: TestClient) -> None:
    def score_of(title: str) -> float:
        return next(j["match"]["score"] for j in stocked.get("/api/jobs").json()["items"] if j["title"] == title)

    before = score_of("Test Manager")
    stocked.patch("/api/profile", json={"preferred_locations": ["Pune"]})
    assert score_of("Test Manager") > before


def test_digest_markdown(stocked: TestClient) -> None:
    r = stocked.get("/api/jobs/digest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"]
    assert "[SYNTHETIC]" in r.text and "not real openings" in r.text
    assert "QA Lead - Payroll Platform" not in r.text  # expired


def test_unknown_job_404_and_auth(stocked: TestClient) -> None:
    assert stocked.get("/api/jobs/00000000-0000-0000-0000-000000000000").status_code == 404
    stocked.post("/api/auth/logout")
    assert stocked.get("/api/jobs").status_code == 401
    assert stocked.post("/api/jobs/refresh").status_code == 401

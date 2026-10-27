import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.connectors.base import JobFilters
from app.models import Application, ApprovalRequest, Document, Job, Resume, User
from app.services import ingestion

PROFILE = {
    "full_name": "Asha Example",
    "preferred_roles": ["QA Lead", "Test Manager", "QA Engineer"],
    "preferred_locations": ["Bengaluru", "Remote"],
    "work_arrangement": "any",
    "total_experience_years": 10,
    "notice_period_days": 60,
    "salary_min": 1_500_000,
    "location": "Bengaluru",
    "summary": "QA lead with HRMS and ERP testing experience across regression and UAT cycles.",
}
SKILLS = [{"name": n} for n in ["Playwright", "Postman", "Functional Testing", "Regression Testing", "UAT", "HRMS"]]


@pytest.fixture
def env(owner: TestClient, db_factory) -> TestClient:
    owner.patch("/api/profile", json=PROFILE)
    owner.put("/api/profile/skills", json=SKILLS)
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        ingestion.run_refresh(db, user, filters=JobFilters(limit=100))  # automation still off: nothing happens
    return owner


def set_rules(c: TestClient, **changes: Any) -> dict:
    rules = c.get("/api/settings/automation").json()
    rules.pop("updated_at", None)
    rules.update(changes)
    r = c.put("/api/settings/automation", json=rules)
    assert r.status_code == 200, r.text
    return r.json()


ON = {"enabled": True, "global_pause": False, "min_match_score": 0}
AUTO = {**ON, "portal_permissions": {"mock": {"enabled": True, "auto_apply": True}}}


def decisions(c: TestClient) -> dict[str, dict]:
    return {d["title"]: d for d in c.get("/api/automation/preview").json()["decisions"]}


def count(db_factory, model) -> int:
    with db_factory() as db:
        return int(db.scalar(select(func.count()).select_from(model)))


# ---------- safe defaults ----------


def test_defaults_do_nothing(env: TestClient, db_factory) -> None:
    p = env.get("/api/automation/preview").json()
    assert p["enabled"] is False and p["global_pause"] is True
    assert p["totals"]["submit"] == 0 and p["totals"]["approval"] == 0
    run = env.post("/api/automation/run").json()
    assert run["status"] == "succeeded" and run["result"]["state"] == "paused"
    assert count(db_factory, Application) == 0 and count(db_factory, ApprovalRequest) == 0


def test_pause_overrides_enable(env: TestClient, db_factory) -> None:
    set_rules(env, enabled=True, global_pause=True, portal_permissions=AUTO["portal_permissions"])
    assert env.post("/api/automation/run").json()["result"]["state"] == "paused"
    assert count(db_factory, Application) == 0


def test_preview_is_a_pure_dry_run(env: TestClient, db_factory) -> None:
    set_rules(env, **AUTO)
    d = decisions(env)
    assert any(x["action"] == "submit" for x in d.values())
    assert count(db_factory, Application) == 0
    assert count(db_factory, ApprovalRequest) == 0
    assert count(db_factory, Document) == 0
    assert count(db_factory, Resume) == 0


# ---------- decisions ----------


def test_auto_apply_off_means_approval_not_submission(env: TestClient, db_factory) -> None:
    set_rules(env, **ON)
    d = decisions(env)
    assert all(x["action"] != "submit" for x in d.values())
    assert any("Auto-apply is off" in r for r in d["Functional Test Lead"]["reasons"])
    res = env.post("/api/automation/run").json()["result"]
    assert res["submitted"] == 0 and res["approvals_created"] > 0
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(Application).where(Application.status == "submitted")) == 0


def test_mandatory_checks_skip(env: TestClient) -> None:
    set_rules(env, **AUTO)
    d = decisions(env)
    assert d["QA Manager"]["action"] == "skip"  # requires 12+ years
    assert any("Not eligible" in r for r in d["QA Manager"]["reasons"])
    assert "QA Lead - Payroll Platform" not in d  # expired listings are not candidates


def test_flagged_screening_answers_need_approval(env: TestClient) -> None:
    set_rules(env, **AUTO)
    d = decisions(env)
    qa_lead = d["QA Lead"]  # asks for expected CTC: a salary commitment
    assert qa_lead["action"] == "approval"
    assert any("Salary commitment" in r for r in qa_lead["reasons"])
    senior = d["Senior QA Engineer"]  # asks a legal work-authorisation question
    assert senior["action"] in {"approval", "skip"}
    if senior["action"] == "approval":
        assert any("Legal declaration" in r for r in senior["reasons"])
    lead = d["Test Automation Lead"]  # only asks notice period, answered from profile
    assert {c["name"]: c["outcome"] for c in lead["checks"]}["screening_answers"] == "pass"


def test_filters(env: TestClient) -> None:
    set_rules(env, **AUTO, allowed_titles=["Lead"], company_blocklist=["Example Payroll Co (Synthetic) Pvt Ltd"])
    d = decisions(env)
    assert (
        d["Test Manager"]["action"] == "skip"
        and "matches none of the allowed titles" in d["Test Manager"]["reasons"][0]
    )
    assert any("blocklisted" in r for r in d["Functional Test Lead"]["reasons"])

    set_rules(env, **AUTO, company_allowlist=["Placeholder Retail Tech (Synthetic)"])
    d = decisions(env)
    assert [t for t, x in d.items() if x["action"] != "skip"] == ["Test Automation Lead"]

    set_rules(env, **AUTO, allowed_locations=["Remote"])
    d = decisions(env)
    assert all(
        x["action"] == "skip"
        for t, x in d.items()
        if t not in {"Senior QA Engineer", "Software Quality Engineering Lead"}
    )

    set_rules(env, **AUTO, min_salary=2_000_000)
    d = decisions(env)
    checks = {c["name"]: c for c in d["Functional Test Lead"]["checks"]}  # salary not disclosed
    assert checks["min_salary"]["outcome"] == "review"
    assert d["Junior Software Tester"]["action"] == "skip"

    set_rules(env, **{**AUTO, "min_match_score": 100})
    assert all(x["action"] == "skip" for x in decisions(env).values())


def test_portal_disabled_skips(env: TestClient) -> None:
    set_rules(env, **ON, portal_permissions={"mock": {"enabled": False, "auto_apply": True}})
    assert all(x["action"] == "skip" for x in decisions(env).values())


# ---------- execution ----------


def test_run_submits_only_clean_jobs_and_is_idempotent(env: TestClient, db_factory) -> None:
    set_rules(env, **AUTO, max_applications_per_day=50)
    expected = {t for t, x in decisions(env).items() if x["action"] == "submit"}
    assert expected and "QA Lead" not in expected
    first = env.post("/api/automation/run").json()["result"]
    assert first["submitted"] == len(expected)
    apps = {a["job_title"]: a for a in env.get("/api/applications").json()}
    for t in expected:
        a = apps[t]
        assert a["status"] == "submitted" and a["is_simulated"] and a["applied_via"] == "simulated"
        assert a["resume_id"] and a["cover_letter_id"]
    assert apps["QA Lead"]["status"] == "draft"  # waiting for approval

    approvals_before = count(db_factory, ApprovalRequest)
    apps_before = count(db_factory, Application)
    second = env.post("/api/automation/run").json()["result"]
    assert second["submitted"] == 0 and second["approvals_created"] == 0
    assert count(db_factory, ApprovalRequest) == approvals_before
    assert count(db_factory, Application) == apps_before
    detail = env.get(f"/api/applications/{apps[next(iter(expected))]['id']}").json()
    sub = [e for e in detail["events"] if e["event_type"] == "submission"]
    assert len(sub) == 1 and sub[0]["details"]["by"] == "automation" and sub[0]["details"]["simulated"]


def test_daily_limit(env: TestClient) -> None:
    set_rules(env, **AUTO, max_applications_per_day=1)
    res = env.post("/api/automation/run").json()["result"]
    assert res["submitted"] == 1
    assert any("Daily limit of 1 reached" in r for d in res["decisions"] for r in d["reasons"])
    assert all(x["action"] != "submit" for x in decisions(env).values())


def test_preferred_resume_is_used(env: TestClient) -> None:
    rid = env.post("/api/resumes/generate", json={}).json()["resume"]["id"]
    set_rules(env, **AUTO, preferred_resume_by_role={"Automation": rid})
    env.post("/api/automation/run")
    app = next(a for a in env.get("/api/applications").json() if a["job_title"] == "Test Automation Lead")
    assert app["resume_id"] == rid


def test_missing_preferred_resume_needs_approval(env: TestClient) -> None:
    set_rules(env, **AUTO, preferred_resume_by_role={"Automation": "00000000-0000-0000-0000-000000000009"})
    d = decisions(env)["Test Automation Lead"]
    assert d["action"] == "approval" and "no longer exists" in d["reasons"][0]


def test_refresh_triggers_automation_when_enabled(env: TestClient, db_factory) -> None:
    set_rules(env, **AUTO)
    env.post("/api/jobs/refresh")
    runs = env.get("/api/jobs/runs").json()
    assert any(r["kind"] == "automation" and r["trigger"] == "after_refresh" for r in runs)


# ---------- approvals ----------


def pending(c: TestClient) -> list[dict]:
    return c.get("/api/approvals?status=pending").json()


def test_approve_requires_review_then_submits(env: TestClient) -> None:
    set_rules(env, **AUTO)
    env.post("/api/automation/run")
    req = next(r for r in pending(env) if r["payload"]["title"] == "QA Lead")
    assert req["kind"] == "application_submission"
    assert req["payload"]["screening_answers_id"] and req["payload"]["cover_letter_id"]
    assert any("Salary commitment" in r for r in req["payload"]["reasons"])
    assert env.post(f"/api/approvals/{req['id']}/approve", json={}).status_code == 400
    r = env.post(f"/api/approvals/{req['id']}/approve", json={"confirm_reviewed": True, "note": "salary ok"})
    assert r.status_code == 200 and r.json()["approval"]["status"] == "approved"
    assert "Simulated submission" in r.json()["outcome"]
    app = env.get(f"/api/applications/{req['subject_id']}").json()
    assert app["status"] == "submitted" and app["is_simulated"]
    assert env.post(f"/api/approvals/{req['id']}/approve", json={"confirm_reviewed": True}).status_code == 409


def test_reject_is_respected_by_later_runs(env: TestClient) -> None:
    set_rules(env, **AUTO)
    env.post("/api/automation/run")
    req = next(r for r in pending(env) if r["payload"]["title"] == "QA Lead")
    r = env.post(f"/api/approvals/{req['id']}/reject", json={"note": "not interested"})
    assert r.status_code == 200 and r.json()["approval"]["status"] == "rejected"
    env.post("/api/automation/run")
    assert not any(p["payload"]["title"] == "QA Lead" for p in pending(env))
    d = decisions(env)["QA Lead"]
    assert d["action"] == "skip" and any("rejected this application earlier" in r for r in d["reasons"])
    app = env.get(f"/api/applications/{req['subject_id']}").json()
    assert app["status"] == "draft"  # nothing submitted


def test_approvals_expire(env: TestClient, db_factory) -> None:
    set_rules(env, **ON)
    env.post("/api/automation/run")
    reqs = pending(env)
    assert len(reqs) >= 2
    with db_factory() as db:
        r = db.get(ApprovalRequest, uuid.UUID(reqs[0]["id"]))
        r.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    # The user applies to another one manually: its approval is settled and expires too.
    env.patch(f"/api/applications/{reqs[1]['subject_id']}", json={"status": "submitted", "confirm_submitted": True})
    statuses = {r["id"]: r["status"] for r in env.get("/api/approvals").json()}
    assert statuses[reqs[0]["id"]] == "expired" and statuses[reqs[1]["id"]] == "expired"
    assert env.post(f"/api/approvals/{reqs[0]['id']}/approve", json={"confirm_reviewed": True}).status_code == 409
    assert env.get("/api/overview").json()["pending_approvals"] == len(reqs) - 2


def test_approval_notification_once(env: TestClient) -> None:
    set_rules(env, **ON)
    env.post("/api/automation/run")
    env.post("/api/automation/run")
    titles = [n["title"] for n in env.get("/api/notifications").json()]
    assert titles.count("Approval needed") == len(pending(env))


# ---------- settings validation ----------


def test_rules_validation(env: TestClient) -> None:
    rules = env.get("/api/settings/automation").json()
    rules.pop("updated_at")
    assert env.put("/api/settings/automation", json={**rules, "portal_permissions": {"monster": {}}}).status_code == 422
    assert (
        env.put(
            "/api/settings/automation", json={**rules, "preferred_resume_by_role": {"lead": "not-a-uuid"}}
        ).status_code
        == 422
    )


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/api/automation/preview").status_code == 401
    assert client.post("/api/automation/run").status_code == 401
    assert client.get("/api/approvals").status_code == 401


def test_jobs_untouched_by_preview(env: TestClient, db_factory) -> None:
    before = count(db_factory, Job)
    env.get("/api/automation/preview")
    assert count(db_factory, Job) == before

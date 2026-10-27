from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.connectors.base import JobFilters, OperationResult
from app.models import Application, ApplicationEvent, Job, Notification, User
from app.services import ingestion


@pytest.fixture
def jobs(owner: TestClient, db_factory) -> dict[str, str]:
    owner.patch("/api/profile", json={"full_name": "Asha Example", "preferred_roles": ["QA Lead"]})
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        ingestion.run_refresh(db, user, filters=JobFilters(limit=100))
        return {j.title: str(j.id) for j in db.scalars(select(Job))}


def create(c: TestClient, job_id: str, **kw):
    return c.post("/api/applications", json={"job_id": job_id, **kw})


def test_create_and_prevent_duplicates(owner: TestClient, jobs, db_factory) -> None:
    r = create(owner, jobs["QA Lead"], notes="Referred by a friend")
    assert r.status_code == 201
    app = r.json()
    assert app["status"] == "draft" and app["portal"] == "mock" and app["job_is_synthetic"]
    assert app["events"][0]["event_type"] == "created"
    dup = create(owner, jobs["QA Lead"])
    assert dup.status_code == 409 and dup.json()["detail"]["existing_id"] == app["id"]
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 1


def test_manual_submission_requires_explicit_confirmation(owner: TestClient, jobs) -> None:
    app = create(owner, jobs["Test Manager"]).json()
    r = owner.patch(f"/api/applications/{app['id']}", json={"status": "submitted"})
    assert r.status_code == 400 and "confirm_submitted" in r.json()["detail"]
    r = owner.patch(f"/api/applications/{app['id']}", json={"status": "submitted", "confirm_submitted": True})
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == "submitted" and a["applied_via"] == "manual" and a["is_simulated"] is False
    assert a["submitted_at"] and a["follow_up_at"]
    assert a["events"][-1]["from_status"] == "draft" and a["events"][-1]["to_status"] == "submitted"


def test_invalid_transitions_rejected(owner: TestClient, jobs) -> None:
    app = create(owner, jobs["QA Lead"]).json()
    assert owner.patch(f"/api/applications/{app['id']}", json={"status": "offer"}).status_code == 409
    assert owner.patch(f"/api/applications/{app['id']}", json={"status": "withdrawn"}).status_code == 200
    r = owner.patch(f"/api/applications/{app['id']}", json={"status": "draft"})
    assert r.status_code == 409  # withdrawn is final
    assert owner.patch(f"/api/applications/{app['id']}", json={"status": "bogus"}).status_code == 422


def test_simulated_submission_is_flagged_and_idempotent(owner: TestClient, jobs) -> None:
    app = create(owner, jobs["QA Lead"]).json()
    r = owner.post(f"/api/applications/{app['id']}/simulate-submit")
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == "submitted" and a["is_simulated"] and a["applied_via"] == "simulated"
    assert a["external_reference"].startswith("MOCK-")
    sub = [e for e in a["events"] if e["event_type"] == "submission"]
    assert sub and sub[0]["details"]["simulated"] is True
    again = owner.post(f"/api/applications/{app['id']}/simulate-submit").json()
    assert again["external_reference"] == a["external_reference"]
    assert len([e for e in again["events"] if e["event_type"] == "submission"]) == 1


def test_uncertain_submission_is_reconciled_not_retried(owner: TestClient, jobs, monkeypatch) -> None:
    from app.connectors.mock import MockConnector

    monkeypatch.setattr(
        MockConnector,
        "submit_application",
        lambda self, app_id: OperationResult(status="unknown", message="timeout", simulated=True),
    )
    app = create(owner, jobs["QA Lead"]).json()
    a = owner.post(f"/api/applications/{app['id']}/simulate-submit").json()
    assert a["status"] == "status_unknown" and a["external_reference"] is None
    # Retrying submission is refused until the status is reconciled.
    assert owner.post(f"/api/applications/{app['id']}/simulate-submit").status_code == 409
    monkeypatch.undo()
    r = owner.post(f"/api/applications/{app['id']}/reconcile")
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    assert owner.post(f"/api/applications/{app['id']}/reconcile").status_code == 409


def test_follow_ups_due_create_one_notification(owner: TestClient, jobs, db_factory) -> None:
    app = create(owner, jobs["QA Lead"]).json()
    owner.patch(f"/api/applications/{app['id']}", json={"status": "submitted", "confirm_submitted": True})
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    a = owner.patch(f"/api/applications/{app['id']}", json={"follow_up_at": past}).json()
    assert a["follow_up_due"] is True
    owner.get("/api/applications")
    owner.get("/api/applications")
    with db_factory() as db:
        n = db.scalars(select(Notification).where(Notification.kind == "follow_up")).all()
        assert len(n) == 1 and n[0].link.endswith(app["id"])
    assert owner.get("/api/overview").json()["follow_ups_due"] == 1
    cleared = owner.patch(f"/api/applications/{app['id']}", json={"follow_up_at": None}).json()
    assert cleared["follow_up_at"] is None and cleared["follow_up_due"] is False


def test_attach_documents_ownership_checked(owner: TestClient, jobs) -> None:
    rid = owner.post("/api/resumes/generate", json={}).json()["resume"]["id"]
    cl = owner.post("/api/documents/cover-letter", json={"job_id": jobs["QA Lead"]}).json()["document"]["id"]
    app = create(owner, jobs["QA Lead"], resume_id=rid, cover_letter_id=cl).json()
    assert app["resume_id"] == rid and app["cover_letter_id"] == cl
    bad = "00000000-0000-0000-0000-000000000001"
    assert create(owner, jobs["Test Manager"], resume_id=bad).status_code == 404
    assert owner.patch(f"/api/applications/{app['id']}", json={"cover_letter_id": bad}).status_code == 404


def test_filters_delete_and_export(owner: TestClient, jobs) -> None:
    a1 = create(owner, jobs["QA Lead"]).json()
    a2 = create(owner, jobs["Test Manager"]).json()
    owner.patch(f"/api/applications/{a2['id']}", json={"status": "submitted", "confirm_submitted": True})
    assert [x["id"] for x in owner.get("/api/applications?status=submitted").json()] == [a2["id"]]
    assert owner.delete(f"/api/applications/{a2['id']}").status_code == 409  # submitted: withdraw instead
    assert owner.delete(f"/api/applications/{a1['id']}").status_code == 204
    export = owner.get("/api/data/export").json()
    assert export["export_format"] == "ai-job-agent/v2"
    assert len(export["applications"]) == 1 and len(export["application_events"]) >= 2
    assert "documents" in export


def test_deleting_account_removes_applications(owner: TestClient, jobs, db_factory) -> None:
    create(owner, jobs["QA Lead"])
    owner.post("/api/data/delete", json={"password": "correct horse battery staple", "confirm": "DELETE MY DATA"})
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 0
        assert db.scalar(select(func.count()).select_from(ApplicationEvent)) == 0

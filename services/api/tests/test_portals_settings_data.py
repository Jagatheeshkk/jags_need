from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.cli import seed_sample_jobs
from app.connectors.base import ConnectorNotSupported, JobFilters
from app.connectors.mock import MockConnector
from app.connectors.registry import get_connector
from app.core.config import Settings
from app.models import AuditLog, CandidateProfile, Job, User
from tests.conftest import PASSWORD

REAL = {"naukri", "linkedin", "indeed", "instahyre", "cutshort"}


def test_portals_listed_honestly(owner: TestClient) -> None:
    portals = {p["code"]: p for p in owner.get("/api/portals").json()}
    assert set(portals) == REAL | {"mock"}
    automated = [
        "search_jobs",
        "get_job_details",
        "get_profile",
        "update_profile",
        "prepare_application",
        "submit_application",
        "get_application_status",
    ]
    for code in REAL:
        assert portals[code]["status"] == "unsupported"  # no automation
        caps = portals[code]["capabilities"]
        assert caps["mode"] == "manual"
        assert not any(caps[k] for k in automated)
        assert "manual_job_capture" in caps["manual_workflows"]
        assert caps["verified_on"] and caps["evidence"]
        assert all(e["url"].startswith("https://") for e in caps["evidence"])
    assert portals["linkedin"]["capabilities"]["verification"] == "terms_reviewed"
    assert portals["naukri"]["capabilities"]["verification"] == "terms_unavailable"
    assert portals["mock"]["capabilities"]["mode"] == "mock"


def test_real_portal_search_refused(owner: TestClient) -> None:
    r = owner.post("/api/portals/linkedin/search", json={"keywords": ["qa"]})
    assert r.status_code == 409
    assert owner.post("/api/portals/nope/search", json={}).status_code == 404


def test_check_connection(owner: TestClient) -> None:
    assert owner.post("/api/portals/mock/check").json()["status"] == "connected"
    assert owner.post("/api/portals/naukri/check").json()["status"] == "unsupported"


def test_mock_search_returns_only_synthetic(owner: TestClient) -> None:
    jobs = owner.post("/api/portals/mock/search", json={"titles": ["lead"], "limit": 50}).json()
    assert jobs and all(j["is_synthetic"] for j in jobs)
    assert all(".invalid/" in j["url"] for j in jobs)
    remote = owner.post("/api/portals/mock/search", json={"work_arrangement": "remote"}).json()
    assert remote and all(j["work_arrangement"] == "remote" for j in remote)


def test_mock_connector_simulates_writes() -> None:
    c = MockConnector()
    r = c.submit_application("app-1")
    assert r.simulated and r.reference and r.reference.startswith("MOCK-")
    assert c.submit_application("app-1").reference == r.reference  # deterministic
    assert c.update_profile({"headline": "x"}).simulated


def test_unverified_connector_refuses_everything() -> None:
    c = get_connector("naukri")
    assert c is not None
    for call in (lambda: c.search_jobs(JobFilters()), lambda: c.submit_application("x"), lambda: c.update_profile({})):
        try:
            call()
            raise AssertionError("should refuse")
        except ConnectorNotSupported:
            pass


def test_seed_sample_jobs_idempotent(owner: TestClient, db_factory, monkeypatch) -> None:
    monkeypatch.setattr("app.cli.get_sessionmaker", lambda: db_factory)
    seed_sample_jobs()
    seed_sample_jobs()
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 11  # 12 listings, 1 repost merged
    ov = owner.get("/api/overview").json()
    assert ov["jobs"] == {"real": 0, "synthetic": 11}


def test_automation_rules_default_safe_and_validated(owner: TestClient) -> None:
    rules = owner.get("/api/settings/automation").json()
    assert rules["enabled"] is False and rules["global_pause"] is True
    assert sum(rules["score_weights"].values()) == 100
    rules.pop("updated_at")
    rules["min_match_score"] = 80
    rules["portal_permissions"] = {"mock": {"enabled": True, "auto_apply": False}}
    r = owner.put("/api/settings/automation", json=rules)
    assert r.status_code == 200 and r.json()["min_match_score"] == 80
    bad = {**rules, "score_weights": {**rules["score_weights"], "compensation_fit": 50}}
    assert owner.put("/api/settings/automation", json=bad).status_code == 422
    assert owner.put("/api/settings/automation", json={**rules, "min_match_score": 101}).status_code == 422


def test_readiness_report(owner: TestClient) -> None:
    rep = owner.get("/api/settings/readiness").json()
    assert rep["paid_dependencies"] == []
    names = {c["name"]: c for c in rep["checks"]}
    assert names["ai_engine"]["status"] == "ok"
    assert names["database"]["status"] in {"ok", "info"}


def test_paid_providers_cannot_be_configured() -> None:
    for field, value in [("ai_provider", "anthropic"), ("email_provider", "sendgrid"), ("storage_backend", "s3")]:
        try:
            Settings(**{field: value})
            raise AssertionError(f"{field}={value} accepted")
        except ValueError:
            pass


def test_cors_origins_from_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://example.vercel.app")
    assert Settings().cors_origins == ["http://localhost:3000", "https://example.vercel.app"]


def test_production_requires_secrets() -> None:
    try:
        Settings(environment="production", database_url="postgresql://u:p@h/db")
        raise AssertionError("insecure production config accepted")
    except ValueError:
        pass
    s = Settings(environment="production", database_url="postgres://u:p@h/db", secret_key="x" * 40, bootstrap_token="t")
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.secure_cookies is True


def test_health_is_public(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_notifications(owner: TestClient) -> None:
    items = owner.get("/api/notifications").json()
    assert len(items) == 1 and items[0]["title"] == "Welcome"
    assert owner.get("/api/overview").json()["unread_notifications"] == 1
    assert owner.post(f"/api/notifications/{items[0]['id']}/read").status_code == 204
    assert owner.get("/api/notifications?unread_only=true").json() == []


def test_export_contains_data_but_no_secrets(owner: TestClient) -> None:
    owner.patch("/api/profile", json={"headline": "QA Lead"})
    r = owner.get("/api/data/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["headline"] == "QA Lead"
    assert "password_hash" not in data["user"]
    assert "argon2" not in r.text
    assert any(a["action"] == "profile.updated" for a in data["audit_logs"])


def test_delete_requires_password_and_confirmation(owner: TestClient, db_factory) -> None:
    owner.patch("/api/profile", json={"headline": "QA Lead"})
    assert owner.post("/api/data/delete", json={"password": PASSWORD, "confirm": "yes"}).status_code == 422
    assert (
        owner.post("/api/data/delete", json={"password": "wrong-password", "confirm": "DELETE MY DATA"}).status_code
        == 400
    )
    r = owner.post("/api/data/delete", json={"password": PASSWORD, "confirm": "DELETE MY DATA"})
    assert r.status_code == 204
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(CandidateProfile)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert owner.get("/api/auth/me").status_code == 401
    assert owner.get("/api/auth/setup-status").json()["setup_required"] is True

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuditLog, User
from app.security.sessions import SESSION_COOKIE
from tests.conftest import EMAIL, PASSWORD


def test_setup_status_then_setup_creates_owner(client: TestClient) -> None:
    assert client.get("/api/auth/setup-status").json() == {"setup_required": True, "bootstrap_token_required": False}
    r = client.post("/api/auth/setup", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 201
    assert r.json()["email"] == EMAIL
    assert "password_hash" not in r.json()
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/auth/setup-status").json()["setup_required"] is False


def test_setup_only_once(owner: TestClient) -> None:
    r = owner.post("/api/auth/setup", json={"email": "other@example.com", "password": PASSWORD})
    assert r.status_code == 409


def test_setup_requires_bootstrap_token_when_configured(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_TOKEN", "bootstrap-secret")
    get_settings.cache_clear()
    try:
        r = client.post("/api/auth/setup", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 403
        r = client.post(
            "/api/auth/setup", json={"email": EMAIL, "password": PASSWORD, "bootstrap_token": "bootstrap-secret"}
        )
        assert r.status_code == 201
    finally:
        monkeypatch.delenv("BOOTSTRAP_TOKEN")
        get_settings.cache_clear()


def test_weak_password_rejected(client: TestClient) -> None:
    r = client.post("/api/auth/setup", json={"email": EMAIL, "password": "short"})
    assert r.status_code == 422


def test_password_is_hashed_with_argon2(owner: TestClient, db_factory) -> None:
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash


def test_login_logout_flow(owner: TestClient) -> None:
    owner.post("/api/auth/logout")
    assert owner.get("/api/auth/me").status_code == 401
    r = owner.post("/api/auth/login", json={"email": EMAIL.upper(), "password": PASSWORD})
    assert r.status_code == 200
    assert owner.get("/api/auth/me").status_code == 200


def test_session_cookie_flags(client: TestClient) -> None:
    r = client.post("/api/auth/setup", json={"email": EMAIL, "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert SESSION_COOKIE in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_wrong_password_and_unknown_user_same_error(owner: TestClient) -> None:
    owner.post("/api/auth/logout")
    a = owner.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password-123"})
    b = owner.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_login_rate_limited(owner: TestClient, db_factory) -> None:
    owner.post("/api/auth/logout")
    for _ in range(3):
        assert owner.post("/api/auth/login", json={"email": EMAIL, "password": "nope-nope-nope"}).status_code == 401
    r = owner.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    with db_factory() as db:
        failed = db.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed")).all()
        assert len(failed) == 3


def test_csrf_required_for_state_changes(owner: TestClient) -> None:
    del owner.headers["x-csrf-token"]
    assert owner.patch("/api/profile", json={"headline": "x"}).status_code == 403
    owner.headers["x-csrf-token"] = "forged"
    assert owner.patch("/api/profile", json={"headline": "x"}).status_code == 403


def test_tampered_session_rejected(owner: TestClient) -> None:
    token = owner.cookies.get(SESSION_COOKIE)
    owner.cookies.set(SESSION_COOKIE, token[:-2] + ("AA" if not token.endswith("AA") else "BB"))
    assert owner.get("/api/auth/me").status_code == 401


def test_change_password_revokes_old_sessions(owner: TestClient) -> None:
    old_cookie = owner.cookies.get(SESSION_COOKIE)
    r = owner.post(
        "/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "a brand new passphrase"}
    )
    assert r.status_code == 204
    assert owner.get("/api/auth/me").status_code == 200  # new cookie issued
    owner.cookies.set(SESSION_COOKIE, old_cookie)
    assert owner.get("/api/auth/me").status_code == 401


def test_logout_all_revokes_sessions(owner: TestClient) -> None:
    cookie = owner.cookies.get(SESSION_COOKIE)
    assert owner.post("/api/auth/logout-all").status_code == 204
    owner.cookies.set(SESSION_COOKIE, cookie)
    assert owner.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/auth/me"),
        ("get", "/api/profile"),
        ("patch", "/api/profile"),
        ("post", "/api/profile/employment"),
        ("put", "/api/profile/skills"),
        ("get", "/api/portals"),
        ("post", "/api/portals/mock/search"),
        ("get", "/api/settings/automation"),
        ("put", "/api/settings/automation"),
        ("get", "/api/settings/readiness"),
        ("get", "/api/overview"),
        ("get", "/api/notifications"),
        ("get", "/api/audit"),
        ("get", "/api/data/export"),
        ("post", "/api/data/delete"),
    ],
)
def test_protected_endpoints_require_auth(client: TestClient, method: str, path: str) -> None:
    r = getattr(client, method)(path) if method == "get" else client.request(method.upper(), path, json={})
    assert r.status_code == 401

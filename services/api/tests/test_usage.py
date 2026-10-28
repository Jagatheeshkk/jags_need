from fastapi.testclient import TestClient

from app.services.usage import classify
from tests.resume_fixtures import make_docx


def test_thresholds() -> None:
    assert classify(10) == "ok"
    assert classify(70) == "warn"
    assert classify(89.9) == "warn"
    assert classify(90) == "fail"


def test_usage_report(owner: TestClient) -> None:
    owner.post("/api/resumes/upload", files={"file": ("cv.docx", make_docx(), "application/octet-stream")})
    r = owner.get("/api/settings/usage").json()
    assert r["row_counts"]["resumes"] == 1
    assert r["uploaded_resume_bytes"] > 30_000  # the synthetic DOCX is ~35 KB
    assert r["limit_bytes"] == 1024 * 1024 * 1024
    if r["database"] == "postgresql":
        assert r["used_bytes"] > 0 and 0 < r["used_percent"] < 70 and r["status"] == "ok"
        assert r["largest_tables"] and "MB of 1024 MB" in r["detail"]
    else:
        assert r["status"] == "info" and r["used_bytes"] is None
    checks = {c["name"]: c for c in owner.get("/api/settings/readiness").json()["checks"]}
    assert checks["database_storage"]["status"] == r["status"]


def test_usage_requires_auth(client: TestClient) -> None:
    assert client.get("/api/settings/usage").status_code == 401

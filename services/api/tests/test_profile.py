from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditLog

FULL_PROFILE = {
    "full_name": "Test Candidate",
    "phone": "+91 98765 43210",
    "location": "Bengaluru",
    "headline": "QA Lead | Functional & Automation Testing",
    "summary": "Synthetic test summary describing a QA lead with HRMS and ERP testing experience.",
    "total_experience_years": 10.5,
    "preferred_roles": ["QA Lead", "Test Manager", "qa lead"],
    "preferred_locations": ["Bengaluru", "Remote"],
    "work_arrangement": "hybrid",
    "salary_min": 2500000,
    "salary_max": 3500000,
    "notice_period_days": 60,
    "excluded_companies": ["Example Blocked Co"],
    "education": [{"institution": "Example University", "degree": "B.E."}],
    "certifications": [{"name": "ISTQB Foundation", "issuer": "ISTQB"}],
    "links": {"linkedin": "https://www.linkedin.com/in/example"},
}

JOB = {
    "company": "Example Corp",
    "title": "QA Lead",
    "start_date": "2020-01-01",
    "is_current": True,
    "achievements": ["Led regression testing"],
}


def test_profile_created_on_first_read(owner: TestClient) -> None:
    p = owner.get("/api/profile").json()
    assert p["email"] == "owner@example.com"
    assert p["full_name"] == "Test Owner"
    assert p["work_arrangement"] == "any"
    assert p["completeness"]["score"] < 50
    assert "Phone number" in p["completeness"]["missing"]


def test_update_profile_and_dedupe(owner: TestClient) -> None:
    r = owner.patch("/api/profile", json=FULL_PROFILE)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["preferred_roles"] == ["QA Lead", "Test Manager"]
    assert p["total_experience_years"] == 10.5
    assert p["education"][0]["institution"] == "Example University"


def test_partial_update_leaves_other_fields(owner: TestClient) -> None:
    owner.patch("/api/profile", json=FULL_PROFILE)
    p = owner.patch("/api/profile", json={"headline": "Test Manager"}).json()
    assert p["headline"] == "Test Manager"
    assert p["location"] == "Bengaluru"


def test_null_resets_non_nullable_fields(owner: TestClient) -> None:
    owner.patch("/api/profile", json=FULL_PROFILE)
    p = owner.patch("/api/profile", json={"preferred_roles": None, "work_arrangement": None}).json()
    assert p["preferred_roles"] == []
    assert p["work_arrangement"] == "any"


def test_profile_validation(owner: TestClient) -> None:
    bad = [
        {"salary_min": 10, "salary_max": 5},
        {"work_arrangement": "moon"},
        {"phone": "call me"},
        {"links": {"site": "javascript:alert(1)"}},
        {"unknown_field": 1},
        {"notice_period_days": -1},
    ]
    for body in bad:
        assert owner.patch("/api/profile", json=body).status_code == 422, body


def test_profile_update_is_audited_without_values(owner: TestClient, db_factory) -> None:
    owner.patch("/api/profile", json={"phone": "+91 11111 22222"})
    with db_factory() as db:
        log = db.scalars(select(AuditLog).where(AuditLog.action == "profile.updated")).one()
        assert log.details == {"fields": ["phone"]}
        assert "11111" not in str(log.details)


def test_employment_crud(owner: TestClient) -> None:
    r = owner.post("/api/profile/employment", json=JOB)
    assert r.status_code == 201, r.text
    emp_id = r.json()["id"]
    upd = {**JOB, "is_current": False, "end_date": "2024-06-30"}
    assert owner.put(f"/api/profile/employment/{emp_id}", json=upd).json()["end_date"] == "2024-06-30"
    assert len(owner.get("/api/profile").json()["employment"]) == 1
    assert owner.delete(f"/api/profile/employment/{emp_id}").status_code == 204
    assert owner.get("/api/profile").json()["employment"] == []
    assert owner.delete(f"/api/profile/employment/{emp_id}").status_code == 404


def test_employment_date_validation(owner: TestClient) -> None:
    cases = [
        {**JOB, "is_current": False},  # missing end date
        {**JOB, "end_date": "2021-01-01"},  # current with end date
        {**JOB, "is_current": False, "end_date": "2019-01-01"},  # end before start
        {**JOB, "start_date": "2999-01-01"},  # future
    ]
    for body in cases:
        assert owner.post("/api/profile/employment", json=body).status_code == 422, body


def test_skills_replace_and_dedupe(owner: TestClient) -> None:
    skills = [
        {"name": "Playwright", "level": "advanced", "years_experience": 3, "is_primary": True},
        {"name": "playwright"},
        {"name": "Postman", "level": "expert"},
        {"name": "Functional Testing", "is_primary": True},
    ]
    p = owner.put("/api/profile/skills", json=skills).json()
    names = [s["name"] for s in p["skills"]]
    assert sorted(names) == ["Functional Testing", "Playwright", "Postman"]
    assert p["skills"][0]["is_primary"] is True
    p = owner.put("/api/profile/skills", json=[{"name": "Postman", "level": "advanced"}]).json()
    assert [(s["name"], s["level"]) for s in p["skills"]] == [("Postman", "advanced")]


def test_complete_profile_scores_100(owner: TestClient) -> None:
    owner.patch("/api/profile", json=FULL_PROFILE)
    owner.post("/api/profile/employment", json=JOB)
    owner.put("/api/profile/skills", json=[{"name": n} for n in ["Selenium", "Playwright", "Postman", "UAT", "HRMS"]])
    c = owner.get("/api/profile").json()["completeness"]
    assert c == {"score": 100, "missing": []}


def test_cannot_touch_another_profiles_employment(owner: TestClient) -> None:
    fake = "00000000-0000-0000-0000-000000000001"
    assert owner.put(f"/api/profile/employment/{fake}", json=JOB).status_code == 404

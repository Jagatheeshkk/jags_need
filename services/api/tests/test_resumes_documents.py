import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.base import JobFilters
from app.models import Job, User
from app.services import ingestion
from app.services.resume_files import UploadRejected, check_upload, safe_filename
from app.services.resume_parser import parse
from tests.resume_fixtures import RESUME_LINES, make_docx, make_pdf, make_zip_bomb

LIMIT = 2 * 1024 * 1024


def upload(c: TestClient, name: str, data: bytes, mime: str = "application/octet-stream"):
    return c.post("/api/resumes/upload", files={"file": (name, data, mime)})


# ---------- validation ----------


def test_safe_filename_strips_paths_and_forces_extension() -> None:
    assert safe_filename("..\\..\\windows\\evil.pdf", ".pdf") == "evil.pdf"
    assert safe_filename("/etc/passwd", ".docx") == "passwd.docx"
    assert safe_filename("my resume (final)!.DOCX", ".docx") == "my resume _final.docx"
    assert safe_filename(None, ".pdf") == "resume.pdf"


@pytest.mark.parametrize(
    "name,data,message",
    [
        ("cv.txt", b"hello", "Only PDF and Word"),
        ("cv.pdf", b"", "empty"),
        ("cv.pdf", b"PK\x03\x04 not really", "valid DOCX"),
        ("cv.docx", b"%PDF-1.4 fake", "content is PDF"),
        ("cv.pdf", b"MZ\x90\x00 executable", "Only PDF and Word"),
        ("cv.pdf", None, "larger than"),
    ],
    ids=["txt", "empty", "fake-docx", "pdf-named-docx", "exe", "too-big"],
)
def test_upload_rejections(name: str, data: bytes | None, message: str) -> None:
    payload = data if data is not None else b"%PDF-" + b"0" * (LIMIT + 1)
    with pytest.raises(UploadRejected, match=message):
        check_upload(name, payload, LIMIT)


def test_zip_bomb_rejected() -> None:
    with pytest.raises(UploadRejected, match="unreasonable size"):
        check_upload("cv.docx", make_zip_bomb(), LIMIT)


def test_encrypted_pdf_rejected() -> None:
    with pytest.raises(UploadRejected, match="Password-protected"):
        check_upload("cv.pdf", make_pdf(encrypt=True), LIMIT)


def test_docx_and_pdf_text_extracted() -> None:
    for name, data in (("cv.docx", make_docx()), ("cv.pdf", make_pdf())):
        f = check_upload(name, data, LIMIT)
        assert "Asha Example" in f.text and "Playwright" in f.text, name


# ---------- parsing ----------


def test_parser_extracts_only_what_is_in_the_text() -> None:
    s = parse("\n".join(RESUME_LINES))
    assert s["full_name"] == "Asha Example"
    assert s["headline"] == "QA Lead | Functional and Automation Testing"
    assert s["email"] == "asha.example@example.com"
    assert s["phone"] == "+91 98765 43210"
    assert s["links"]["linkedin"].startswith("https://")
    assert s["total_experience_years"] == 10
    assert {"Playwright", "Selenium", "Postman", "UAT", "Test Strategy", "HRMS", "ERP"} <= set(s["skills"])
    assert "Python" not in s["skills"]
    jobs = s["employment"]
    assert jobs[0]["start_date"] == "2020-01-01" and jobs[0]["is_current"] and jobs[0]["end_date"] is None
    assert jobs[1]["start_date"] == "2016-03-01" and jobs[1]["end_date"] == "2019-12-01"
    assert "Example HR Cloud" in jobs[0]["heading"]
    assert s["certifications"] == ["ISTQB Foundation Level"]
    assert {"summary", "experience", "skills", "education", "certifications"} <= set(s["sections_found"])


def test_parser_on_empty_text() -> None:
    s = parse("")
    assert s["full_name"] is None and s["skills"] == [] and s["employment"] == []


# ---------- upload API ----------


def test_upload_parse_and_apply(owner: TestClient) -> None:
    original = make_docx()
    r = upload(owner, "Asha CV.docx", original)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["duplicate"] is False and body["resume"]["kind"] == "uploaded"
    assert len(body["resume"]["sha256"]) == 64
    assert body["suggestions"]["email"] == "asha.example@example.com"
    # Nothing is applied automatically.
    assert owner.get("/api/profile").json()["skills"] == []

    rid = body["resume"]["id"]
    applied = owner.post(
        f"/api/resumes/{rid}/apply",
        json={
            "profile": {"headline": "QA Lead | Functional and Automation Testing", "total_experience_years": 10},
            "add_skills": ["Playwright", "Postman"],
            "add_education": [{"institution": "Example University", "degree": "B.E."}],
        },
    )
    assert applied.status_code == 200, applied.text
    p = applied.json()
    assert p["headline"].startswith("QA Lead") and p["total_experience_years"] == 10
    assert {s["name"] for s in p["skills"]} == {"Playwright", "Postman"}
    assert p["education"][0]["institution"] == "Example University"
    assert p["phone"] is None  # not ticked, not applied

    dup = upload(owner, "copy.docx", original)
    assert dup.status_code == 200 and dup.json()["duplicate"] is True and dup.json()["resume"]["id"] == rid

    dl = owner.get(f"/api/resumes/{rid}/download?format=docx")
    assert dl.status_code == 200 and dl.content == original  # stored bytes returned unchanged
    assert 'filename="Asha_CV.docx"' in dl.headers["content-disposition"]
    assert owner.get(f"/api/resumes/{rid}/download?format=pdf").status_code == 409


def test_upload_rejected_via_api(owner: TestClient) -> None:
    r = upload(owner, "cv.docx", b"%PDF-1.4 fake")
    assert r.status_code == 422 and "content is PDF" in r.json()["detail"]
    assert owner.get("/api/resumes").json() == []


def test_apply_rejects_unknown_fields(owner: TestClient) -> None:
    rid = upload(owner, "cv.pdf", make_pdf()).json()["resume"]["id"]
    assert owner.post(f"/api/resumes/{rid}/apply", json={"profile": {"password_hash": "x"}}).status_code == 422


# ---------- generation ----------

PROFILE = {
    "full_name": "Asha Example",
    "email": "asha.example@example.com",
    "phone": "+91 98765 43210",
    "location": "Bengaluru",
    "headline": "QA Lead",
    "summary": "QA lead with HRMS and ERP testing experience across regression and UAT cycles.",
    "preferred_roles": ["QA Lead"],
    "preferred_locations": ["Bengaluru"],
    "salary_min": 2500000,
    "salary_max": 3500000,
    "notice_period_days": 60,
    "certifications": [{"name": "ISTQB Foundation", "issuer": "ISTQB"}],
}
SKILLS = [
    {"name": "Playwright", "years_experience": 3, "is_primary": True},
    {"name": "Postman"},
    {"name": "Regression Testing"},
    {"name": "UAT"},
    {"name": "Java"},
]
EMPLOYMENT = {
    "company": "Example HR Cloud",
    "title": "QA Lead",
    "start_date": "2016-01-01",
    "is_current": True,
    "achievements": ["Mentored 4 testers", "Cut regression time by 40% with Playwright and Postman suites"],
}


@pytest.fixture
def ready(owner: TestClient, db_factory) -> tuple[TestClient, dict[str, str]]:
    owner.patch("/api/profile", json=PROFILE)
    owner.put("/api/profile/skills", json=SKILLS)
    owner.post("/api/profile/employment", json=EMPLOYMENT)
    with db_factory() as db:
        user = db.scalars(select(User)).one()
        ingestion.run_refresh(db, user, filters=JobFilters(limit=100))
        jobs = {j.title: str(j.id) for j in db.scalars(select(Job))}
    return owner, jobs


def test_master_and_tailored_resume_versions(ready) -> None:
    c, jobs = ready
    m = c.post("/api/resumes/generate", json={})
    assert m.status_code == 201 and m.json()["created"]
    master = m.json()["resume"]
    assert master["kind"] == "master" and master["version"] == 1
    again = c.post("/api/resumes/generate", json={})
    assert again.status_code == 200 and again.json()["resume"]["id"] == master["id"]  # identical: no new version

    c.patch("/api/profile", json={"headline": "QA Lead | HRMS"})
    v2 = c.post("/api/resumes/generate", json={}).json()["resume"]
    assert v2["version"] == 2 and v2["sha256"] != master["sha256"]

    t = c.post("/api/resumes/generate", json={"job_id": jobs["QA Lead"]}).json()["resume"]
    assert t["kind"] == "tailored" and t["parent_resume_id"] == v2["id"] and t["target_role"] == "QA Lead"
    content = c.get(f"/api/resumes/{t['id']}").json()["content_json"]
    # Matched skills come first; skills the job wants but the profile lacks are NOT added.
    assert content["skills"] == ["Playwright", "Postman", "Regression Testing", "UAT", "Java"]
    assert "test strategy" not in " ".join(content["skills"]).lower()
    assert "Relevant to the QA Lead role" in content["summary"]
    ach = content["experience"][0]["achievements"]
    assert ach[0].startswith("Cut regression time")  # most job-relevant achievement first


def test_resume_downloads_render(ready) -> None:
    c, _ = ready
    rid = c.post("/api/resumes/generate", json={}).json()["resume"]["id"]
    docx_bytes = c.get(f"/api/resumes/{rid}/download?format=docx").content
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        xml = z.read("word/document.xml").decode()
    assert "Asha Example" in xml and "Example HR Cloud" in xml
    pdf = c.get(f"/api/resumes/{rid}/download?format=pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF-")
    from pypdf import PdfReader

    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Asha Example" in text and "ISTQB Foundation" in text


def test_pdf_escapes_markup_in_user_text(ready) -> None:
    c, _ = ready
    c.patch("/api/profile", json={"headline": "QA <b>Lead</b> & <font size=40>Tester"})
    rid = c.post("/api/resumes/generate", json={}).json()["resume"]["id"]
    pdf = c.get(f"/api/resumes/{rid}/download?format=pdf")
    assert pdf.status_code == 200
    from pypdf import PdfReader

    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "<b>Lead</b>" in text


def test_generation_requires_name(owner: TestClient) -> None:
    owner.patch("/api/profile", json={"full_name": ""})
    assert owner.post("/api/resumes/generate", json={}).status_code == 409


def test_cover_letter_uses_profile_facts_only(ready) -> None:
    c, jobs = ready
    r = c.post("/api/documents/cover-letter", json={"job_id": jobs["QA Lead"]})
    assert r.status_code == 201
    doc = r.json()["document"]
    text = " ".join(doc["content"]["paragraphs"])
    assert doc["content"]["greeting"] == "Dear Hiring Team at Example HR Cloud (Synthetic),"
    assert "In my current role as QA Lead at Example HR Cloud" in text
    assert "Playwright" in text and "Postman" in text
    assert "Java" not in text  # profile skill the job does not ask for
    assert "Test Strategy" not in text and "test strategy" not in text  # job skill the profile lacks
    assert "HRMS" in text
    assert "notice period is 60 days" in text

    edited = c.put(
        f"/api/documents/{doc['id']}",
        json={"greeting": "Dear Ms Example,", "paragraphs": ["Short and sweet."], "sign_off": "Thanks,"},
    )
    assert edited.status_code == 201
    e = edited.json()["document"]
    assert e["version"] == 2 and e["content"]["edited"] is True and e["content"]["paragraphs"] == ["Short and sweet."]
    assert len(c.get(f"/api/documents?job_id={jobs['QA Lead']}&kind=cover_letter").json()) == 2
    for fmt, magic in (("docx", b"PK"), ("pdf", b"%PDF-")):
        assert c.get(f"/api/documents/{e['id']}/download?format={fmt}").content.startswith(magic)


def test_screening_answers_flag_what_needs_you(ready) -> None:
    c, jobs = ready
    questions = [
        "What is your notice period?",
        "What is your expected CTC?",
        "Are you legally authorized to work in India?",
        "How many years of experience do you have with Playwright?",
        "Do you have experience with Cypress?",
        "Are you willing to relocate to Pune?",
        "What is your current location?",
        "Do you have experience with Postman?",
        "Describe your favourite bug.",
    ]
    r = c.post("/api/documents/screening-answers", json={"job_id": jobs["QA Lead"], "questions": questions})
    assert r.status_code == 201
    a = {x["question"]: x for x in r.json()["document"]["content"]["answers"]}
    assert a[questions[0]]["answer"] == "60 days" and not a[questions[0]]["needs_confirmation"]
    assert a[questions[1]]["answer"] == "INR 2,500,000 – 3,500,000 per year" and a[questions[1]]["needs_confirmation"]
    assert a[questions[2]]["answer"] is None and a[questions[2]]["category"] == "sensitive"
    assert a[questions[3]]["answer"] == "3 years"
    assert a[questions[4]]["answer"] is None and "not in your profile" in a[questions[4]]["reason"]
    assert a[questions[5]]["answer"] is None and a[questions[5]]["needs_confirmation"]
    assert a[questions[6]]["answer"] == "Bengaluru"
    assert a[questions[7]]["needs_confirmation"]  # in profile, but years unknown
    assert a[questions[8]]["category"] == "unknown" and a[questions[8]]["answer"] is None
    assert r.json()["document"]["content"]["needs_review"] == 6
    pdf = c.get(f"/api/documents/{r.json()['document']['id']}/download?format=pdf")
    assert pdf.content.startswith(b"%PDF-")


def test_documents_are_private_and_validated(ready) -> None:
    c, jobs = ready
    assert c.post("/api/documents/screening-answers", json={"questions": []}).status_code == 422
    assert (
        c.post("/api/documents/cover-letter", json={"job_id": "00000000-0000-0000-0000-000000000000"}).status_code
        == 404
    )
    assert c.get("/api/documents/00000000-0000-0000-0000-000000000000").status_code == 404
    rid = c.post("/api/resumes/generate", json={}).json()["resume"]["id"]
    c.post("/api/auth/logout")
    assert c.get(f"/api/resumes/{rid}/download").status_code == 401
    assert c.get("/api/documents").status_code == 401

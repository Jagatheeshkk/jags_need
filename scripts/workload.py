"""Exercise a running API the way a day of real use would, and report latencies.

Used by scripts/resource-check.ps1 against a throwaway, resource-limited container. It creates
the owner account on a fresh database with a random test password, so never point it at a
database you care about.

    python scripts/workload.py http://127.0.0.1:8099
"""

import io
import json
import secrets
import statistics
import sys
import time

import httpx


def docx_bytes() -> bytes:
    import docx

    d = docx.Document()
    for line in ["Workload Tester", "QA Lead", "workload@example.com", "Experience",
                 "QA Lead, Example Co  Jan 2018 - Present", "Skills", "Playwright, Postman, UAT"] * 20:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def main(base: str) -> int:
    timings: dict[str, list[float]] = {}
    c = httpx.Client(base_url=base, timeout=120)

    def call(name: str, method: str, path: str, **kw) -> httpx.Response:
        t = time.perf_counter()
        r = c.request(method, path, **kw)
        timings.setdefault(name, []).append(time.perf_counter() - t)
        if r.status_code >= 400:
            raise SystemExit(f"{name} failed: {r.status_code} {r.text[:200]}")
        return r

    token = call("csrf", "GET", "/api/auth/csrf").json()["csrf_token"]
    c.headers["x-csrf-token"] = token
    if not call("setup-status", "GET", "/api/auth/setup-status").json()["setup_required"]:
        raise SystemExit("Database already has an owner: use a fresh, throwaway database.")
    call("setup", "POST", "/api/auth/setup", json={"email": "workload@example.com",
                                                    "password": secrets.token_urlsafe(18), "display_name": "W"})
    call("profile", "PATCH", "/api/profile", json={
        "full_name": "Workload Tester", "headline": "QA Lead", "preferred_roles": ["QA Lead", "Test Manager"],
        "total_experience_years": 10, "notice_period_days": 60, "salary_min": 1500000,
        "summary": "QA lead with HRMS and ERP testing experience across regression and UAT cycles."})
    call("skills", "PUT", "/api/profile/skills", json=[{"name": n} for n in ["Playwright", "Postman", "UAT", "HRMS"]])
    call("upload", "POST", "/api/resumes/upload", files={"file": ("cv.docx", docx_bytes(), "application/octet-stream")})
    call("refresh", "POST", "/api/jobs/refresh")
    jobs = call("list jobs", "GET", "/api/jobs?limit=100").json()["items"]
    for _ in range(5):
        call("list jobs", "GET", "/api/jobs?limit=100")
    rid = call("generate resume", "POST", "/api/resumes/generate", json={}).json()["resume"]["id"]
    for j in jobs[:5]:
        call("tailored resume", "POST", "/api/resumes/generate", json={"job_id": j["id"]})
        call("cover letter", "POST", "/api/documents/cover-letter", json={"job_id": j["id"]})
        call("job detail", "GET", f"/api/jobs/{j['id']}")
    for _ in range(5):
        call("download pdf", "GET", f"/api/resumes/{rid}/download?format=pdf")
        call("download docx", "GET", f"/api/resumes/{rid}/download?format=docx")
    call("automation preview", "GET", "/api/automation/preview")
    call("digest", "GET", "/api/jobs/digest")
    call("export", "GET", "/api/data/export")
    call("usage", "GET", "/api/settings/usage")

    summary = {
        name: {"n": len(v), "median_ms": round(statistics.median(v) * 1000), "max_ms": round(max(v) * 1000)}
        for name, v in timings.items()
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"))

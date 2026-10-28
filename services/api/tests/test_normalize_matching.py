from datetime import UTC, date, datetime, timedelta

from app.models import CandidateProfile, CandidateSkill, EmploymentHistory, Job, Skill
from app.services import taxonomy
from app.services.matching import UNKNOWN_CREDIT, RuleBasedMatchEngine, candidate_years, eligibility
from app.services.normalize import canonical_url, clean_text, company_key, freshness

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


# ---------- normalisation ----------


def test_canonical_url_strips_tracking_and_noise() -> None:
    a = canonical_url("HTTP://WWW.Example.com/jobs/123/?utm_source=x&ref=abc&id=7#apply")
    b = canonical_url("https://example.com/jobs/123?id=7")
    assert a == b == "https://example.com/jobs/123?id=7"
    assert canonical_url("javascript:alert(1)") is None
    assert canonical_url(None) is None


def test_company_key_drops_legal_suffixes() -> None:
    assert company_key("Example HR Cloud Pvt. Ltd.") == company_key("example hr cloud") == "example hr cloud"


def test_clean_text_removes_control_chars_and_limits() -> None:
    assert clean_text("a\x00b\x07  c", 100) == "ab c"
    assert clean_text("x" * 50, 10) == "x" * 10
    assert clean_text("   ", 10) is None


def test_freshness_bands() -> None:
    assert freshness(NOW - timedelta(days=1), None, now=NOW) == "new"
    assert freshness(NOW - timedelta(days=10), None, now=NOW) == "fresh"
    assert freshness(NOW - timedelta(days=20), None, now=NOW) == "aging"
    assert freshness(NOW - timedelta(days=40), None, now=NOW) == "stale"
    assert freshness(None, None, now=NOW) == "unknown"
    assert freshness(NOW - timedelta(days=1), NOW - timedelta(hours=1), now=NOW) == "expired"
    assert freshness(NOW.replace(tzinfo=None) - timedelta(days=1), None, now=NOW) == "new"  # naive = UTC


def test_taxonomy_phrases_and_canonical_skills() -> None:
    found = taxonomy.find_phrases(
        "Own User Acceptance Testing and REST API testing with Postman", taxonomy.SKILL_SYNONYMS
    )
    assert {"uat", "api testing", "postman"} <= found
    assert "regression testing" not in taxonomy.find_phrases("linear regression models", taxonomy.SKILL_SYNONYMS)
    assert taxonomy.canonical_skill("User Acceptance Testing") == "uat"
    assert taxonomy.canonical_skill("Something Unusual") == "something unusual"


# ---------- matching ----------


def make_profile(**kw) -> CandidateProfile:
    skills = kw.pop(
        "skills",
        [
            "Playwright",
            "Postman",
            "Functional Testing",
            "Regression Testing",
            "UAT",
            "Test Strategy",
            "Team Leadership",
            "HRMS",
        ],
    )
    p = CandidateProfile(
        full_name="Test",
        preferred_roles=["QA Lead"],
        preferred_locations=["Bengaluru"],
        work_arrangement="hybrid",
        salary_currency="INR",
        salary_min=2_000_000,
        excluded_companies=[],
        education=[],
        certifications=[],
        links={},
        search_keywords=[],
        total_experience_years=10,
    )
    for k, v in kw.items():
        setattr(p, k, v)
    p.skills = [CandidateSkill(skill=Skill(name=s.lower(), display_name=s)) for s in skills]
    if "employment" not in kw:
        p.employment = []
    return p


def make_job(**kw) -> Job:
    base = dict(
        title="QA Lead",
        company="Example HR Cloud",
        location="Bengaluru",
        work_arrangement="hybrid",
        description="Lead QA for an HRMS product. Regression and UAT planning, Playwright and Postman.",
        skills=["Functional Testing", "Regression Testing", "UAT", "Playwright", "Postman", "Team Leadership"],
        salary_min=2_200_000,
        salary_max=3_000_000,
        salary_currency="INR",
        experience_min=8,
        experience_max=12,
        posted_at=NOW - timedelta(days=1),
        expires_at=None,
        status="active",
        updated_at=NOW,
    )
    base.update(kw)
    return Job(**base)


def test_strong_match_scores_high_and_explains() -> None:
    r = RuleBasedMatchEngine().score(make_profile(), make_job())
    assert r.score >= 85
    assert all(c.status == "match" for c in r.components.values()), r.components
    assert "Playwright" in r.matched_skills
    assert r.missing_skills == []
    assert r.eligibility["status"] == "eligible"
    assert "rule-based" in r.explanation


def test_weights_must_sum_and_score_is_weighted() -> None:
    w = {
        "skills_experience": 100,
        "role_responsibilities": 0,
        "domain_experience": 0,
        "location_work_arrangement": 0,
        "compensation_fit": 0,
    }
    p = make_profile(skills=["Playwright"])
    r = RuleBasedMatchEngine().score(p, make_job(), w)
    skill = r.components["skills_experience"].score
    assert r.score == round(skill * 100, 1)


def test_unknown_data_is_neutral_not_a_match() -> None:
    p = make_profile(salary_min=None, preferred_locations=[], location=None)
    job = make_job(salary_min=None, salary_max=None, description="Lead QA.", company="Acme")
    r = RuleBasedMatchEngine().score(p, job)
    comp = r.components["compensation_fit"]
    assert comp.status == "unknown" and comp.score == UNKNOWN_CREDIT
    assert r.components["domain_experience"].status == "unknown"
    assert r.components["location_work_arrangement"].status == "unknown"
    assert "not as a match" in r.explanation


def test_non_qa_role_and_missing_skills() -> None:
    job = make_job(title="Data Engineer", description="Spark and Airflow pipelines", skills=["Spark", "Airflow"])
    r = RuleBasedMatchEngine().score(make_profile(), job)
    assert r.components["role_responsibilities"].status == "mismatch"
    assert set(r.missing_skills) == {"spark", "airflow"}
    assert r.score <= 30
    assert "outside QA/testing" in r.explanation


def test_location_and_arrangement() -> None:
    eng = RuleBasedMatchEngine()
    remote = eng.score(make_profile(work_arrangement="any"), make_job(work_arrangement="remote", location=None))
    assert remote.components["location_work_arrangement"].status == "match"
    elsewhere = eng.score(make_profile(), make_job(location="Pune"))
    assert elsewhere.components["location_work_arrangement"].status == "mismatch"
    onsite = eng.score(make_profile(work_arrangement="remote"), make_job(work_arrangement="onsite"))
    assert onsite.components["location_work_arrangement"].score == 0


def test_compensation_below_minimum() -> None:
    r = RuleBasedMatchEngine().score(make_profile(salary_min=4_000_000), make_job(salary_max=3_000_000))
    assert r.components["compensation_fit"].status == "mismatch"
    other = RuleBasedMatchEngine().score(make_profile(), make_job(salary_currency="USD"))
    assert other.components["compensation_fit"].status == "unknown"


def test_eligibility_is_separate_from_score() -> None:
    p = make_profile(excluded_companies=["Example HR Cloud Pvt Ltd"])
    r = RuleBasedMatchEngine().score(p, make_job())
    assert r.eligibility["status"] == "ineligible"
    assert r.score >= 85  # still a good fit on paper; eligibility decides separately
    junior = make_profile(total_experience_years=3)
    assert eligibility(junior, make_job())["status"] == "ineligible"
    unknown = make_profile(total_experience_years=None)
    assert eligibility(unknown, make_job())["status"] == "unknown"
    expired = make_job(expires_at=datetime.now(UTC) - timedelta(days=1))
    assert eligibility(make_profile(), expired)["status"] == "ineligible"


def test_candidate_years_merges_overlapping_roles() -> None:
    p = make_profile(total_experience_years=None)
    p.employment = [
        EmploymentHistory(company="A", title="QA", start_date=date(2016, 1, 1), end_date=date(2020, 1, 1)),
        EmploymentHistory(company="B", title="QA", start_date=date(2019, 1, 1), end_date=date(2022, 1, 1)),
    ]
    assert candidate_years(p) == 6.0


def test_no_skills_means_unknown_skills() -> None:
    r = RuleBasedMatchEngine().score(make_profile(skills=[]), make_job())
    assert r.components["skills_experience"].status == "unknown"
    assert r.matched_skills == []


def test_inputs_hash_changes_with_profile() -> None:
    a = RuleBasedMatchEngine().score(make_profile(), make_job()).inputs_hash
    b = RuleBasedMatchEngine().score(make_profile(salary_min=1), make_job()).inputs_hash
    assert a != b


def test_location_key() -> None:
    from app.services.normalize import location_key

    assert location_key(" Bengaluru,  Karnataka ") == "bengaluru karnataka"
    assert location_key("CHENNAI") == location_key("chennai") == "chennai"
    assert location_key(None) == location_key("") == ""

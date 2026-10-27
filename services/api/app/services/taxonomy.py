"""Small, editable vocabulary used by the rule-based matcher.

Each canonical skill lists phrases that mean the same thing. Matching is phrase-based on
normalised text, so 'User Acceptance Testing' in a description counts as 'uat'.
"""

import re

SKILL_SYNONYMS: dict[str, list[str]] = {
    "manual testing": ["manual testing", "manual qa", "manual test"],
    "functional testing": ["functional testing", "functional test", "functional qa"],
    "regression testing": ["regression testing", "regression test", "regression suite"],
    "system testing": ["system testing", "system test"],
    "integration testing": ["integration testing", "integration test"],
    "smoke testing": ["smoke testing", "smoke test", "smoke suite"],
    "sanity testing": ["sanity testing", "sanity test", "sanity suite"],
    "uat": ["uat", "user acceptance testing", "user acceptance test", "acceptance testing"],
    "test automation": ["test automation", "automation testing", "automation framework", "automated testing"],
    "playwright": ["playwright"],
    "selenium": ["selenium", "webdriver"],
    "api testing": ["api testing", "api test", "api automation", "rest api testing"],
    "postman": ["postman"],
    "performance testing": ["performance testing", "load testing", "performance test", "jmeter"],
    "contract testing": ["contract testing", "pact"],
    "test planning": ["test planning", "test plan", "test plans"],
    "test strategy": ["test strategy", "testing strategy", "qa strategy"],
    "test execution": ["test execution", "executing test cases", "test case execution"],
    "test management": ["test management", "managing testing", "qa management", "quality management"],
    "defect management": ["defect management", "defect triage", "bug triage", "defect tracking", "defect logging"],
    "root cause analysis": ["root cause analysis", "rca"],
    "sdlc": ["sdlc", "software development life cycle"],
    "stlc": ["stlc", "software testing life cycle"],
    "agile": ["agile", "scrum", "kanban"],
    "team leadership": [
        "team leadership",
        "lead a team",
        "lead team",
        "leading a team",
        "team lead",
        "mentor",
        "mentoring",
        "people management",
        "grow a qa team",
        "hire and grow",
    ],
    "stakeholder communication": [
        "stakeholder communication",
        "stakeholder management",
        "stakeholder reporting",
        "business stakeholders",
        "stakeholders",
    ],
    "release management": ["release management", "release readiness"],
    "typescript": ["typescript"],
    "python": ["python"],
    "java": ["java"],
    "sql": ["sql"],
    "ci": ["ci", "continuous integration", "ci/cd", "jenkins", "github actions"],
}

DOMAINS: dict[str, list[str]] = {
    "hrms": ["hrms", "hris", "human resources", "hr platform", "hr cloud", "hcm"],
    "payroll": ["payroll"],
    "erp": ["erp", "sap", "oracle ebs", "supply-chain", "supply chain"],
    "fintech": ["fintech", "banking", "payments", "financial services"],
    "healthcare": ["healthcare", "health platform", "clinical", "hospital"],
    "retail": ["retail", "e-commerce", "ecommerce"],
    "logistics": ["logistics", "shipping", "fleet"],
}

# Words that mark a QA/testing role and the seniority of it.
ROLE_FAMILY = {"qa", "quality", "test", "testing", "tester", "sdet"}
SENIORITY = {
    "lead": 3,
    "manager": 4,
    "head": 5,
    "senior": 2,
    "sr": 2,
    "principal": 4,
    "architect": 4,
    "junior": 0,
    "jr": 0,
    "associate": 1,
    "intern": 0,
}


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9+#/]+", " ", text.lower()).strip() + " "


def words(text: str) -> list[str]:
    return _norm(text).split()


def find_phrases(text: str | None, vocab: dict[str, list[str]]) -> set[str]:
    """Return canonical keys whose phrases appear as whole words in text."""
    if not text:
        return set()
    hay = _norm(text)
    return {key for key, phrases in vocab.items() if any(_norm(p) in hay for p in phrases)}


def canonical_skill(name: str) -> str:
    """Map a free-text skill to its canonical key when known, else its normalised form."""
    found = find_phrases(name, SKILL_SYNONYMS)
    norm = " ".join(name.lower().split())
    if norm in SKILL_SYNONYMS:
        return norm
    return min(found) if len(found) == 1 else norm


_ACRONYMS = {"uat", "api", "sdlc", "stlc", "ci", "sql", "hrms", "erp", "qa", "rca"}
_PROPER = {
    "typescript": "TypeScript",
    "fintech": "FinTech",
    "postman": "Postman",
    "playwright": "Playwright",
    "selenium": "Selenium",
    "python": "Python",
    "java": "Java",
}


def display_skill(key: str) -> str:
    """'api testing' -> 'API Testing', 'hrms' -> 'HRMS'."""
    if key in _PROPER:
        return _PROPER[key]
    return " ".join(w.upper() if w in _ACRONYMS else w.capitalize() for w in key.split())

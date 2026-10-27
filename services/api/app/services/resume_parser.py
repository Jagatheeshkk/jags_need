"""Best-effort, rule-based extraction of profile suggestions from resume text.

Nothing here changes the profile. The result is a list of suggestions the user reviews and
chooses to apply. Values are only ever copied from the resume text, never guessed beyond it.
"""

import re
from typing import Any

from app.services import taxonomy

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{8,16}\d)(?!\d)")
_URL = re.compile(r"https?://[^\s,;)]+|(?:www\.)?(?:linkedin\.com|github\.com)/[^\s,;)]+", re.I)
_YEARS = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs)\b(?:\s+of)?(?:\s+\w+){0,3}\s+experience", re.I)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_RANGE = re.compile(rf"({_DATE})\s*(?:-|–|—|to)\s*({_DATE}|present|current|now|till date)", re.I)
_MONTHS = {
    m: i
    for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}

SECTION_HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "about me", "objective", "career objective"],
    "experience": [
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "work history",
        "career history",
    ],
    "skills": ["skills", "technical skills", "key skills", "core skills", "core competencies", "tools"],
    "education": ["education", "academic qualifications", "qualifications", "education and training"],
    "certifications": ["certifications", "certificates", "licenses and certifications", "certification"],
}


def _heading(line: str) -> str | None:
    norm = re.sub(r"[^a-z ]", "", line.lower()).strip()
    if not norm or len(norm) > 40:
        return None
    for key, names in SECTION_HEADINGS.items():
        if norm in names:
            return key
    return None


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        key = _heading(line)
        if key:
            current = key
            sections.setdefault(key, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _to_iso(token: str) -> str | None:
    t = token.strip().lower()
    if t in {"present", "current", "now", "till date"}:
        return None
    m = re.match(rf"({_MONTH})\s+(\d{{4}})", t)
    if m:
        return f"{m.group(2)}-{_MONTHS[m.group(1)[:3]]:02d}-01"
    m = re.match(r"(\d{1,2})/(\d{4})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}-01"
    m = re.match(r"(\d{4})$", t)
    return f"{m.group(1)}-01-01" if m else None


def _employment(section: str) -> list[dict[str, Any]]:
    """Lines with a date range become entries; the nearby text is kept raw for the user to split."""
    lines = [ln for ln in section.splitlines() if ln.strip()]
    out = []
    for i, line in enumerate(lines):
        m = _RANGE.search(line)
        if not m:
            continue
        label = (line[: m.start()] + line[m.end() :]).strip(" |,-–—()")
        if not label and i > 0:
            label = lines[i - 1].strip()
        end_token = m.group(2)
        out.append(
            {
                "heading": label[:300],
                "start_date": _to_iso(m.group(1)),
                "end_date": _to_iso(end_token),
                "is_current": end_token.strip().lower() in {"present", "current", "now", "till date"},
                "date_text": m.group(0),
            }
        )
    return out[:20]


def parse(text: str) -> dict[str, Any]:
    sections = split_sections(text)
    header_lines = [ln for ln in sections.get("header", "").splitlines() if ln.strip()]
    name = None
    if header_lines:
        first = header_lines[0]
        if 2 <= len(first.split()) <= 5 and re.fullmatch(r"[A-Za-z .'-]+", first):
            name = first.strip()
    headline = None
    for ln in header_lines[1:4]:
        if not _EMAIL.search(ln) and not _PHONE.search(ln) and not _URL.search(ln) and 3 <= len(ln) <= 150:
            headline = ln
            break

    email = _EMAIL.search(text)
    phone = _PHONE.search(sections.get("header", text[:1000]))
    links: dict[str, str] = {}
    for url in _URL.findall(text):
        full = url if url.lower().startswith("http") else f"https://{url}"
        full = full.replace("http://", "https://", 1)
        key = "linkedin" if "linkedin.com" in full else "github" if "github.com" in full else f"link{len(links) + 1}"
        links.setdefault(key, full[:500])
        if len(links) >= 5:
            break

    skill_keys = taxonomy.find_phrases(text, taxonomy.SKILL_SYNONYMS)
    domain_keys = taxonomy.find_phrases(text, taxonomy.DOMAINS)
    years = _YEARS.search(text)
    certs = [ln.strip("•-* ").strip() for ln in sections.get("certifications", "").splitlines() if ln.strip()]

    return {
        "full_name": name,
        "headline": headline,
        "email": email.group(0) if email else None,
        "phone": re.sub(r"\s+", " ", phone.group(1)).strip() if phone else None,
        "links": links,
        "summary": sections.get("summary"),
        "total_experience_years": float(years.group(1)) if years else None,
        "skills": sorted(taxonomy.display_skill(k) for k in skill_keys | domain_keys),
        "employment": _employment(sections.get("experience", "")),
        "certifications": [c[:200] for c in certs[:20]],
        "education_text": sections.get("education"),
        "sections_found": sorted(k for k in sections if k != "header"),
    }

"""Rule-based generation of resumes, cover letters and screening-answer drafts.

Factual accuracy rule: every fact comes from the candidate profile. Job text is used only to
choose ordering and emphasis (e.g. which of *your* skills to list first). Skills, dates,
employers, certifications, salaries and achievements are never invented. A guard verifies
generated resumes before they are stored.
"""

import hashlib
import json
import re
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, Document, Job, Resume, User
from app.services import taxonomy
from app.services.matching import candidate_skill_keys, candidate_years, job_skill_keys

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FactCheckFailed(Exception):
    pass


def content_sha(content: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


def _fmt_month(d: date | None) -> str:
    return d.strftime("%b %Y") if d else "Present"


def _relevance(text: str, keys: set[str]) -> int:
    return len(taxonomy.find_phrases(text, taxonomy.SKILL_SYNONYMS) & keys)


# ---------------------------------------------------------------- resumes


def build_resume(profile: CandidateProfile, job: Job | None = None) -> dict[str, Any]:
    job_keys = job_skill_keys(job) if job else set()
    mine = candidate_skill_keys(profile)  # canonical -> display, as entered by the user
    primary = {cs.skill.display_name for cs in profile.skills if cs.is_primary}

    def skill_rank(display: str) -> tuple[int, int, str]:
        key = taxonomy.canonical_skill(display)
        return (0 if key in job_keys else 1, 0 if display in primary else 1, display.lower())

    skills = sorted(mine.values(), key=skill_rank)
    matched = [d for d in skills if taxonomy.canonical_skill(d) in job_keys]

    experience = []
    for e in sorted(profile.employment, key=lambda x: (x.is_current, x.start_date), reverse=True):
        achievements = [str(a) for a in (e.achievements or [])]
        if job_keys:
            # Stable sort: most job-relevant achievements first, original order otherwise.
            achievements = sorted(achievements, key=lambda a: -_relevance(a, job_keys))
        experience.append(
            {
                "title": e.title,
                "company": e.company,
                "location": e.location,
                "start": e.start_date.isoformat(),
                "end": e.end_date.isoformat() if e.end_date else None,
                "dates": f"{_fmt_month(e.start_date)} – {'Present' if e.is_current else _fmt_month(e.end_date)}",
                "description": e.description,
                "achievements": achievements,
            }
        )

    summary = profile.summary or ""
    if job and matched:
        # Only restates skills already in the profile that this listing also asks for.
        summary = (
            f"{summary}\n\nRelevant to the {job.title} role: hands-on experience with {', '.join(matched[:6])}.".strip()
        )

    content: dict[str, Any] = {
        "type": "resume",
        "name": profile.full_name,
        "headline": profile.headline,
        "contact": {
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "links": dict(profile.links or {}),
        },
        "summary": summary or None,
        "skills": skills,
        "experience": experience,
        "education": list(profile.education or []),
        "certifications": list(profile.certifications or []),
        "target": {"job_id": str(job.id), "title": job.title, "company": job.company} if job else None,
    }
    verify_resume_facts(content, profile)
    return content


def verify_resume_facts(content: dict[str, Any], profile: CandidateProfile) -> None:
    """Refuse to store a resume containing skills, employers or certifications not in the profile."""
    allowed_skills = {cs.skill.display_name for cs in profile.skills}
    extra = set(content["skills"]) - allowed_skills
    if extra:
        raise FactCheckFailed(f"skills not in profile: {sorted(extra)}")
    allowed_jobs = {(e.company, e.title) for e in profile.employment}
    if any((x["company"], x["title"]) not in allowed_jobs for x in content["experience"]):
        raise FactCheckFailed("employment entry not in profile")
    allowed_certs = {json.dumps(c, sort_keys=True) for c in profile.certifications or []}
    if any(json.dumps(c, sort_keys=True) not in allowed_certs for c in content["certifications"]):
        raise FactCheckFailed("certification not in profile")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60] or "resume"


def save_generated_resume(db: Session, user: User, content: dict[str, Any], job: Job | None) -> tuple[Resume, bool]:
    """Store a new version unless identical content already exists. Returns (resume, created)."""
    sha = content_sha(content)
    existing = db.scalars(select(Resume).where(Resume.user_id == user.id, Resume.sha256 == sha)).first()
    if existing:
        return existing, False
    kind = "tailored" if job else "master"
    label = f"{job.title} – {job.company}" if job else "Master resume"
    version = (
        db.scalar(select(func.max(Resume.version)).where(Resume.user_id == user.id, Resume.label == label)) or 0
    ) + 1
    parent = None
    if job:
        parent = db.scalars(
            select(Resume).where(Resume.user_id == user.id, Resume.kind == "master").order_by(Resume.version.desc())
        ).first()
    from app.services.render import render_resume

    size = len(render_resume(content, "docx"))
    r = Resume(
        user_id=user.id,
        label=label[:200],
        kind=kind,
        version=version,
        job_id=job.id if job else None,
        target_role=job.title[:200] if job else None,
        parent_resume_id=parent.id if parent else None,
        file_name=f"{_slug(content.get('name') or 'resume')}-{_slug(label)}-v{version}.docx",
        mime_type=DOCX_MIME,
        size_bytes=size,
        sha256=sha,
        content=None,
        content_json=content,
    )
    db.add(r)
    db.flush()
    return r, True


# ---------------------------------------------------------------- cover letters


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def build_cover_letter(profile: CandidateProfile, job: Job) -> dict[str, Any]:
    job_keys = job_skill_keys(job)
    mine = candidate_skill_keys(profile)
    matched = [mine[k] for k in sorted(job_keys) if k in mine][:5]
    years = candidate_years(profile)
    roles = sorted(profile.employment, key=lambda e: (e.is_current, e.start_date), reverse=True)
    latest = roles[0] if roles else None
    shared_domains = taxonomy.find_phrases(
        f"{job.title} {job.company} {job.description or ''}", taxonomy.DOMAINS
    ) & taxonomy.find_phrases(
        " ".join(
            [profile.summary or "", profile.headline or ""]
            + [f"{e.title} {e.company} {e.description or ''}" for e in profile.employment]
            + [cs.skill.display_name for cs in profile.skills]
        ),
        taxonomy.DOMAINS,
    )

    paragraphs = [f"I am writing to apply for the {job.title} position at {job.company}."]
    background = []
    if latest:
        role_phrase = "In my current role" if latest.is_current else "Most recently"
        background.append(f"{role_phrase} as {latest.title} at {latest.company}")
    if years is not None:
        background.append(f"I bring {years:g} years of experience")
    if background:
        paragraphs.append(", ".join(background) + ".")
    if matched:
        paragraphs.append(f"My experience with {_join(matched)} lines up with what this role asks for.")
    if shared_domains:
        paragraphs.append(
            f"I have worked on {_join(sorted(d.upper() for d in shared_domains))} products, "
            "so I understand the business context."
        )
    achievement = next((str(a) for e in roles for a in (e.achievements or [])), None)
    if achievement:
        paragraphs.append(f"For example: {achievement.rstrip('.')}.")
    closing = "I would welcome the chance to discuss how I can contribute to your team."
    if profile.notice_period_days is not None:
        closing += f" My notice period is {profile.notice_period_days} days."
    paragraphs.append(closing)
    return {
        "type": "cover_letter",
        "greeting": f"Dear Hiring Team at {job.company},",
        "paragraphs": paragraphs,
        "sign_off": "Kind regards,",
        "name": profile.full_name,
        "contact": {"email": profile.email, "phone": profile.phone},
        "target": {"job_id": str(job.id), "title": job.title, "company": job.company},
        "facts_used": {"matched_skills": matched, "years": years, "latest_role": latest.title if latest else None},
    }


# ---------------------------------------------------------------- screening answers

_SENSITIVE = re.compile(
    r"authori[sz]ed to work|work permit|visa|sponsor|citizen|criminal|convict|background check|disabilit|veteran|"
    r"gender|race|ethnic|religio|caste|marital|pregnan|declar|certify|attest|consent|true and correct|legal",
    re.I,
)
_SALARY = re.compile(r"salary|ctc|compensation|expected pay|pay expectation|current pay", re.I)
_NOTICE = re.compile(r"notice period|how soon|join(?:ing)? date|earliest start|start date", re.I)
_TOTAL_YEARS = re.compile(r"(how many|total|overall) years|years of (total |overall )?experience", re.I)
_LOCATION = re.compile(r"current (city|location)|where are you (based|located)|which city", re.I)
_RELOCATE = re.compile(r"relocat", re.I)
_ARRANGEMENT = re.compile(r"remote|hybrid|on-?site|work from office|in office", re.I)
_SKILL_Q = re.compile(
    r"(?:experience|years|worked|familiar|proficien|expertise)\b.*?\b(?:with|in|using|on)\s+(.+?)\??$", re.I
)


def _answer(question: str, profile: CandidateProfile) -> dict[str, Any]:
    q = question.strip()

    def out(answer: str | None, category: str, confirm: bool, reason: str) -> dict[str, Any]:
        return {"question": q, "answer": answer, "category": category, "needs_confirmation": confirm, "reason": reason}

    if _SENSITIVE.search(q):
        return out(None, "sensitive", True, "Legal declaration or sensitive attestation: answer this yourself.")
    if _SALARY.search(q):
        if profile.salary_min is None and profile.salary_max is None:
            return out(None, "salary", True, "No salary expectation in your profile.")
        rng = " – ".join(f"{v:,}" for v in (profile.salary_min, profile.salary_max) if v is not None)
        return out(
            f"{profile.salary_currency} {rng} per year", "salary", True, "Salary commitment: confirm before submitting."
        )
    if _NOTICE.search(q):
        if profile.notice_period_days is None:
            return out(None, "notice_period", True, "No notice period in your profile.")
        return out(f"{profile.notice_period_days} days", "notice_period", False, "From your profile.")
    if _RELOCATE.search(q):
        return out(None, "relocation", True, "Your relocation preference is not recorded.")
    if _LOCATION.search(q):
        if not profile.location:
            return out(None, "location", True, "No current location in your profile.")
        return out(profile.location, "location", False, "From your profile.")
    if _ARRANGEMENT.search(q) and not _SKILL_Q.search(q):
        pref = profile.work_arrangement
        if pref == "any":
            return out(
                "Yes, I am open to remote, hybrid or on-site work.",
                "work_arrangement",
                False,
                "From your profile (any arrangement).",
            )
        return out(
            f"My preference is {pref} work.", "work_arrangement", True, "Check that this answers the question asked."
        )
    m = _SKILL_Q.search(q)
    if m:
        wanted = m.group(1).strip(" .?")
        key = taxonomy.canonical_skill(wanted)
        for cs in profile.skills:
            if taxonomy.canonical_skill(cs.skill.display_name) == key:
                if cs.years_experience is not None:
                    return out(
                        f"{float(cs.years_experience):g} years",
                        "skill",
                        False,
                        f"From your profile skill '{cs.skill.display_name}'.",
                    )
                return out(
                    f"Yes, I have experience with {cs.skill.display_name}.",
                    "skill",
                    True,
                    "Years for this skill are not recorded in your profile.",
                )
        return out(None, "skill", True, f"'{wanted}' is not in your profile skills.")
    if _TOTAL_YEARS.search(q):
        years = candidate_years(profile)
        if years is None:
            return out(None, "experience", True, "Total experience is not in your profile.")
        return out(f"{years:g} years", "experience", False, "From your profile.")
    return out(None, "unknown", True, "No rule matches this question: answer it yourself.")


def build_screening_answers(profile: CandidateProfile, questions: list[str], job: Job | None) -> dict[str, Any]:
    answers = [_answer(q, profile) for q in questions if q.strip()]
    return {
        "type": "screening_answers",
        "target": {"job_id": str(job.id), "title": job.title, "company": job.company} if job else None,
        "answers": answers,
        "needs_review": sum(1 for a in answers if a["needs_confirmation"]),
    }


# ---------------------------------------------------------------- persistence


def save_document(
    db: Session, user: User, kind: str, content: dict[str, Any], job: Job | None, title: str
) -> tuple[Document, bool]:
    sha = content_sha(content)
    existing = db.scalars(select(Document).where(Document.user_id == user.id, Document.sha256 == sha)).first()
    if existing:
        return existing, False
    stmt = select(func.max(Document.version)).where(Document.user_id == user.id, Document.kind == kind)
    stmt = stmt.where(Document.job_id == job.id) if job else stmt.where(Document.job_id.is_(None))
    version = (db.scalar(stmt) or 0) + 1
    d = Document(
        user_id=user.id,
        job_id=job.id if job else None,
        kind=kind,
        title=title[:300],
        version=version,
        content=content,
        sha256=sha,
    )
    db.add(d)
    db.flush()
    return d, True

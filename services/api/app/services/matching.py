"""Deterministic, explainable job matching. Needs no API key or network.

Every component scores 0..1 with a status:
  match / partial / mismatch  - decided from data on both sides
  unknown                     - data missing on either side; scores a neutral 0.5 and is
                                reported as unknown, never as a confirmed match
Eligibility (expired listing, excluded company, minimum experience) is evaluated separately
and does not change the score.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from app.core.scoring import DEFAULT_SCORE_WEIGHTS
from app.models import CandidateProfile, Job
from app.services import taxonomy
from app.services.normalize import company_key, freshness, jaccard

ENGINE_VERSION = "rule_based/1"
UNKNOWN_CREDIT = 0.5
OUT_OF_FAMILY_CAP = 30.0

Status = Literal["match", "partial", "mismatch", "unknown"]


@dataclass
class Component:
    score: float
    status: Status
    detail: str


@dataclass
class MatchResult:
    score: float
    components: dict[str, Component]
    matched_skills: list[str]
    missing_skills: list[str]
    eligibility: dict[str, Any]
    explanation: str
    inputs_hash: str
    engine: str = ENGINE_VERSION
    weights: dict[str, int] = field(default_factory=dict)

    def breakdown(self) -> dict[str, Any]:
        return {
            "inputs_hash": self.inputs_hash,
            "components": {
                k: {
                    "weight": self.weights.get(k, 0),
                    "score": round(c.score, 3),
                    "status": c.status,
                    "detail": c.detail,
                }
                for k, c in self.components.items()
            },
        }


class MatchEngine(Protocol):
    """Provider-independent interface. An optional local-model engine can implement this later."""

    name: str

    def score(self, profile: CandidateProfile, job: Job, weights: dict[str, int]) -> MatchResult: ...


def _status(score: float) -> Status:
    return "match" if score >= 0.8 else "partial" if score >= 0.4 else "mismatch"


def _unknown(detail: str) -> Component:
    return Component(UNKNOWN_CREDIT, "unknown", detail)


def candidate_skill_keys(profile: CandidateProfile) -> dict[str, str]:
    """canonical key -> display name, from skills the user entered (never inferred)."""
    return {taxonomy.canonical_skill(cs.skill.display_name): cs.skill.display_name for cs in profile.skills}


def job_skill_keys(job: Job) -> set[str]:
    keys = {taxonomy.canonical_skill(s) for s in (job.skills or []) if isinstance(s, str) and s.strip()}
    keys |= taxonomy.find_phrases(f"{job.title}\n{job.description or ''}", taxonomy.SKILL_SYNONYMS)
    return keys


def candidate_years(profile: CandidateProfile, today: date | None = None) -> float | None:
    if profile.total_experience_years is not None:
        return float(profile.total_experience_years)
    if not profile.employment:
        return None
    today = today or date.today()
    # Merge overlapping spans so concurrent roles are not double counted.
    spans = sorted((e.start_date, e.end_date or today) for e in profile.employment)
    total, cur_start, cur_end = 0.0, spans[0][0], spans[0][1]
    for start, end in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += (cur_end - cur_start).days
            cur_start, cur_end = start, end
    total += (cur_end - cur_start).days
    return round(total / 365.25, 1)


def _experience_fit(years: float | None, job: Job) -> tuple[float | None, str]:
    lo, hi = job.experience_min, job.experience_max
    if years is None or (lo is None and hi is None):
        return None, "experience requirement or your total experience is unknown"
    if lo is not None and years < lo:
        return max(0.0, 1 - 0.25 * (lo - years)), f"{years:g} yrs vs {lo}+ required"
    if hi is not None and years > hi + 2:
        return 0.8, f"{years:g} yrs is above the {lo or 0}-{hi} yr range"
    return 1.0, f"{years:g} yrs fits the {lo or 0}-{hi if hi is not None else '+'} yr range"


def _skills_component(profile: CandidateProfile, job: Job, cand: dict[str, str]) -> tuple[Component, list, list]:
    required = job_skill_keys(job)
    matched = sorted(k for k in required if k in cand)
    missing = sorted(k for k in required if k not in cand)
    exp_score, exp_detail = _experience_fit(candidate_years(profile), job)
    if not required:
        skill_score, skill_detail = None, "the listing names no recognisable skills"
    elif not cand:
        skill_score, skill_detail = None, "your profile has no skills yet"
    else:
        skill_score = len(matched) / len(required)
        skill_detail = f"{len(matched)} of {len(required)} listed skills"
    if skill_score is None and exp_score is None:
        return _unknown(f"{skill_detail}; {exp_detail}"), matched, missing
    parts = [(0.7, skill_score), (0.3, exp_score)]
    score = sum(w * (UNKNOWN_CREDIT if s is None else s) for w, s in parts)
    status: Status = "unknown" if skill_score is None else _status(score)
    return Component(score, status, f"{skill_detail}; {exp_detail}"), matched, missing


def _title_tokens(title: str) -> set[str]:
    mapped = {
        "testing": "qa",
        "test": "qa",
        "quality": "qa",
        "tester": "qa",
        "engineering": "engineer",
        "management": "manager",
        "sr": "senior",
        "jr": "junior",
    }
    words = taxonomy.words(title)
    return {mapped.get(w, w) for w in words}


def _seniority(tokens: set[str]) -> int | None:
    levels = [taxonomy.SENIORITY[t] for t in tokens if t in taxonomy.SENIORITY]
    return max(levels) if levels else None


def _role_component(profile: CandidateProfile, job: Job) -> Component:
    prefs = [r for r in profile.preferred_roles if isinstance(r, str) and r.strip()]
    if not prefs:
        return _unknown("no preferred roles in your profile")
    job_tokens = _title_tokens(job.title)
    if not job_tokens & (taxonomy.ROLE_FAMILY | {"qa"}):
        return Component(0.0, "mismatch", f"'{job.title}' is not a QA/testing role")
    best, best_role = 0.0, prefs[0]
    for role in prefs:
        role_tokens = _title_tokens(role)
        sim = jaccard(job_tokens, role_tokens)
        js, rs = _seniority(job_tokens), _seniority(role_tokens)
        seniority = 0.5 if js is None or rs is None else max(0.0, 1 - 0.35 * abs(js - rs))
        score = 0.5 * sim + 0.5 * seniority
        if score > best:
            best, best_role = score, role
    best = min(1.0, best + 0.15)  # same role family already established
    return Component(best, _status(best), f"'{job.title}' vs your preferred role '{best_role}'")


def _candidate_text(profile: CandidateProfile) -> str:
    parts = [profile.headline or "", profile.summary or ""]
    for e in profile.employment:
        parts += [e.title, e.company, e.description or "", " ".join(map(str, e.achievements or []))]
    parts += [cs.skill.display_name for cs in profile.skills]
    return "\n".join(parts)


def _domain_component(profile: CandidateProfile, job: Job) -> Component:
    job_domains = taxonomy.find_phrases(f"{job.title}\n{job.company}\n{job.description or ''}", taxonomy.DOMAINS)
    if not job_domains:
        return _unknown("the listing does not name a business domain")
    mine = taxonomy.find_phrases(_candidate_text(profile), taxonomy.DOMAINS)
    if not mine:
        return _unknown(f"listing domain {', '.join(sorted(job_domains)).upper()}; none found in your profile")
    shared = job_domains & mine
    if shared:
        return Component(1.0, "match", f"{', '.join(sorted(shared)).upper()} experience matches")
    return Component(0.0, "mismatch", f"listing domain {', '.join(sorted(job_domains)).upper()} not in your profile")


def _location_component(profile: CandidateProfile, job: Job) -> Component:
    want = profile.work_arrangement or "any"
    prefs = [p.lower() for p in profile.preferred_locations if isinstance(p, str)]
    if profile.location:
        prefs.append(profile.location.lower())
    arr = (job.work_arrangement or "").lower() or None
    if arr == "remote":
        if want in {"remote", "any"} or "remote" in prefs:
            return Component(1.0, "match", "remote role and you accept remote work")
        return Component(0.5, "partial", f"remote role; you prefer {want}")
    if arr is None and not job.location:
        return _unknown("work arrangement and location not stated")
    arr_score = (
        1.0 if want == "any" or arr is None or want == arr else 0.5 if {want, arr} == {"hybrid", "onsite"} else 0.0
    )
    loc = (job.location or "").lower()
    if not loc:
        return Component(arr_score * 0.5 + 0.25, "unknown", f"{arr} role; location not stated")
    real_prefs = [p for p in prefs if p != "remote"]
    if not real_prefs:
        return _unknown(f"{arr or 'unstated arrangement'} role in {job.location}; you have no preferred locations")
    loc_ok = any(p in loc or loc in p for p in real_prefs)
    score = arr_score if loc_ok else 0.15 * arr_score
    where = f"{arr or 'unstated arrangement'} role in {job.location}"
    return Component(score, _status(score), f"{where} {'matches' if loc_ok else 'is outside'} your preferred locations")


def _compensation_component(profile: CandidateProfile, job: Job) -> Component:
    if profile.salary_min is None:
        return _unknown("no minimum salary in your profile")
    top = job.salary_max or job.salary_min
    if top is None:
        return _unknown("salary not disclosed")
    if job.salary_currency and job.salary_currency != profile.salary_currency:
        return _unknown(f"salary in {job.salary_currency}, your expectation is in {profile.salary_currency}")
    if top >= profile.salary_min:
        return Component(1.0, "match", f"up to {top:,} meets your minimum of {profile.salary_min:,}")
    ratio = top / profile.salary_min
    score = max(0.0, (ratio - 0.7) / 0.3)
    return Component(score, _status(score), f"up to {top:,} is below your minimum of {profile.salary_min:,}")


def eligibility(profile: CandidateProfile, job: Job, now: datetime | None = None) -> dict[str, Any]:
    blocking: list[str] = []
    unknown: list[str] = []
    if freshness(job.posted_at, job.expires_at, job.status, now) == "expired":
        blocking.append("The listing has expired.")
    excluded = {company_key(c) for c in profile.excluded_companies if isinstance(c, str)}
    if company_key(job.company) in excluded:
        blocking.append(f"{job.company} is in your excluded companies.")
    years = candidate_years(profile)
    if job.experience_min is not None:
        if years is None:
            unknown.append(f"Requires {job.experience_min}+ years; your total experience is not in your profile.")
        elif years < job.experience_min:
            blocking.append(f"Requires {job.experience_min}+ years; your profile shows {years:g}.")
    status = "ineligible" if blocking else "unknown" if unknown else "eligible"
    return {"status": status, "reasons": blocking + unknown}


def inputs_hash(profile: CandidateProfile, weights: dict[str, int]) -> str:
    """Fingerprint of everything that affects a score; when it changes, matches are recomputed."""
    payload = {
        "engine": ENGINE_VERSION,
        "weights": weights,
        "skills": sorted(cs.skill.display_name.lower() for cs in profile.skills),
        "years": str(profile.total_experience_years),
        "employment": sorted((str(e.start_date), str(e.end_date)) for e in profile.employment),
        "text": _candidate_text(profile),
        "prefs": [
            profile.preferred_roles,
            profile.preferred_locations,
            profile.work_arrangement,
            profile.location,
            profile.salary_min,
            profile.salary_currency,
            profile.excluded_companies,
        ],
        "day": datetime.now(UTC).date().isoformat(),  # freshness/expiry and ongoing roles change daily
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class RuleBasedMatchEngine:
    name = ENGINE_VERSION

    def score(self, profile: CandidateProfile, job: Job, weights: dict[str, int] | None = None) -> MatchResult:
        weights = weights or dict(DEFAULT_SCORE_WEIGHTS)
        cand = candidate_skill_keys(profile)
        skills, matched, missing = _skills_component(profile, job, cand)
        components = {
            "skills_experience": skills,
            "role_responsibilities": _role_component(profile, job),
            "domain_experience": _domain_component(profile, job),
            "location_work_arrangement": _location_component(profile, job),
            "compensation_fit": _compensation_component(profile, job),
        }
        total = sum(weights.get(k, 0) * c.score for k, c in components.items())
        score = round(total / max(1, sum(weights.values())) * 100, 1)
        if components["role_responsibilities"].detail.endswith("is not a QA/testing role"):
            # Location or salary fit must not make an unrelated role look like a good match.
            score = min(score, OUT_OF_FAMILY_CAP)
        elig = eligibility(profile, job)
        return MatchResult(
            score=score,
            components=components,
            matched_skills=[cand[k] for k in matched],
            missing_skills=missing,
            eligibility=elig,
            explanation=_explain(score, components, matched, missing, cand, elig),
            inputs_hash=inputs_hash(profile, weights),
            weights=weights,
        )


_LABELS = {
    "skills_experience": "Skills and experience",
    "role_responsibilities": "Role",
    "domain_experience": "Domain",
    "location_work_arrangement": "Location and work arrangement",
    "compensation_fit": "Compensation",
}


def _explain(
    score: float,
    components: dict[str, Component],
    matched: list[str],
    missing: list[str],
    cand: dict[str, str],
    elig: dict[str, Any],
) -> str:
    lines = [f"Score {score:g}/100 from your profile data only (rule-based, no AI service)."]
    if components["role_responsibilities"].detail.endswith("is not a QA/testing role"):
        lines.append(f"Capped at {OUT_OF_FAMILY_CAP:g} because the role is outside QA/testing.")
    if matched:
        lines.append(f"Matched skills: {', '.join(cand[k] for k in matched)}.")
    if missing:
        lines.append(f"Listed skills not in your profile: {', '.join(missing)}.")
    for key, c in components.items():
        lines.append(f"{_LABELS[key]}: {c.status} - {c.detail}.")
    unknown = [_LABELS[k] for k, c in components.items() if c.status == "unknown"]
    if unknown:
        lines.append(f"Unknown (counted as neutral, not as a match): {', '.join(unknown)}.")
    if elig["status"] != "eligible":
        lines.append(f"Eligibility {elig['status']}: {' '.join(elig['reasons'])}")
    return "\n".join(lines)


def get_engine() -> MatchEngine:
    # Only the rule-based engine exists today; an optional local model can be added behind
    # the same interface and must fall back to this one when unavailable.
    return RuleBasedMatchEngine()

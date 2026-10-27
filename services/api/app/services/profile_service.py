import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import CandidateProfile, CandidateSkill, EmploymentHistory, User
from app.repositories import profiles as repo
from app.schemas.profile import (
    Completeness,
    EmploymentIn,
    EmploymentOut,
    ProfileOut,
    ProfileUpdate,
    SkillIn,
    SkillOut,
)
from app.services import audit

# Columns that are NOT NULL: sending null in an update resets them to these values.
_NON_NULL_DEFAULTS: dict[str, Any] = {
    "full_name": str,
    "preferred_roles": list,
    "preferred_locations": list,
    "excluded_companies": list,
    "education": list,
    "certifications": list,
    "links": dict,
    "work_arrangement": lambda: "any",
    "salary_currency": lambda: "INR",
    "search_keywords": list,
    "refresh_interval_hours": lambda: 24,
}


def get_or_create(db: Session, user: User) -> CandidateProfile:
    profile = repo.get_profile(db, user.id)
    if profile is None:
        db.add(CandidateProfile(user_id=user.id, email=user.email, full_name=user.display_name))
        db.commit()
        profile = repo.get_profile(db, user.id)
        assert profile is not None
    return profile


def completeness(profile: CandidateProfile) -> Completeness:
    checks: list[tuple[str, bool]] = [
        ("Full name", bool(profile.full_name.strip())),
        ("Contact email", bool(profile.email)),
        ("Phone number", bool(profile.phone)),
        ("Current location", bool(profile.location)),
        ("Professional headline", bool(profile.headline)),
        ("Professional summary (50+ characters)", len(profile.summary or "") >= 50),
        ("At least one employment entry", len(profile.employment) >= 1),
        ("At least five skills", len(profile.skills) >= 5),
        ("Education", len(profile.education) >= 1),
        ("Preferred roles", len(profile.preferred_roles) >= 1),
        ("Preferred locations", len(profile.preferred_locations) >= 1),
        ("Notice period", profile.notice_period_days is not None),
        ("Salary expectation", profile.salary_min is not None or profile.salary_max is not None),
    ]
    passed = sum(1 for _, ok in checks if ok)
    return Completeness(score=round(passed * 100 / len(checks)), missing=[label for label, ok in checks if not ok])


def to_out(profile: CandidateProfile) -> ProfileOut:
    skills = [
        SkillOut(
            id=cs.id,
            name=cs.skill.display_name,
            level=cs.level,
            years_experience=float(cs.years_experience) if cs.years_experience is not None else None,
            is_primary=cs.is_primary,
        )
        for cs in sorted(profile.skills, key=lambda s: (not s.is_primary, s.skill.name))
    ]
    data: dict[str, Any] = {
        c: getattr(profile, c) for c in ProfileUpdate.model_fields if c not in {"total_experience_years"}
    }
    exp = profile.total_experience_years
    return ProfileOut(
        id=profile.id,
        total_experience_years=float(exp) if exp is not None else None,
        employment=[EmploymentOut.model_validate(e) for e in profile.employment],
        skills=skills,
        completeness=completeness(profile),
        **data,
    )


def update(db: Session, user: User, changes: ProfileUpdate, request: Request) -> CandidateProfile:
    profile = get_or_create(db, user)
    fields = changes.model_dump(exclude_unset=True, mode="json")
    changed = []
    for name, value in fields.items():
        if value is None and name in _NON_NULL_DEFAULTS:
            value = _NON_NULL_DEFAULTS[name]()
        if getattr(profile, name) != value:
            setattr(profile, name, value)
            changed.append(name)
    if changed:
        # Field names only: personal values are not copied into the audit log.
        audit.record(
            db,
            "profile.updated",
            user_id=user.id,
            entity_type="candidate_profile",
            entity_id=profile.id,
            details={"fields": sorted(changed)},
            request=request,
        )
        db.commit()
        db.refresh(profile)
    return profile


def add_employment(db: Session, user: User, data: EmploymentIn, request: Request) -> EmploymentHistory:
    profile = get_or_create(db, user)
    row = EmploymentHistory(profile_id=profile.id, **data.model_dump())
    db.add(row)
    db.flush()
    audit.record(
        db, "employment.created", user_id=user.id, entity_type="employment_history", entity_id=row.id, request=request
    )
    db.commit()
    return row


def update_employment(
    db: Session, user: User, employment_id: uuid.UUID, data: EmploymentIn, request: Request
) -> EmploymentHistory | None:
    profile = get_or_create(db, user)
    row = repo.get_employment(db, profile.id, employment_id)
    if row is None:
        return None
    for k, v in data.model_dump().items():
        setattr(row, k, v)
    audit.record(
        db, "employment.updated", user_id=user.id, entity_type="employment_history", entity_id=row.id, request=request
    )
    db.commit()
    return row


def delete_employment(db: Session, user: User, employment_id: uuid.UUID, request: Request) -> bool:
    profile = get_or_create(db, user)
    row = repo.get_employment(db, profile.id, employment_id)
    if row is None:
        return False
    db.delete(row)
    audit.record(
        db,
        "employment.deleted",
        user_id=user.id,
        entity_type="employment_history",
        entity_id=employment_id,
        request=request,
    )
    db.commit()
    return True


def replace_skills(db: Session, user: User, skills: list[SkillIn], request: Request) -> CandidateProfile:
    profile = get_or_create(db, user)
    wanted: dict[str, SkillIn] = {}
    for s in skills:
        wanted.setdefault(" ".join(s.name.lower().split()), s)

    existing = {cs.skill.name: cs for cs in profile.skills}
    for name, old in existing.items():
        if name not in wanted:
            profile.skills.remove(old)
    for name, s in wanted.items():
        found = existing.get(name)
        if found is None:
            skill = repo.get_or_create_skill(db, s.name)
            found = CandidateSkill(skill_id=skill.id, skill=skill)
            profile.skills.append(found)
        cs = found
        cs.level = s.level
        cs.years_experience = s.years_experience
        cs.is_primary = s.is_primary
    audit.record(
        db,
        "skills.replaced",
        user_id=user.id,
        entity_type="candidate_profile",
        entity_id=profile.id,
        details={"count": len(wanted)},
        request=request,
    )
    db.commit()
    db.expire_all()
    refreshed = repo.get_profile(db, user.id)
    assert refreshed is not None
    return refreshed

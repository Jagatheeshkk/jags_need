import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CandidateProfile, CandidateSkill, EmploymentHistory, Skill


def get_profile(db: Session, user_id: uuid.UUID) -> CandidateProfile | None:
    stmt = (
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id)
        .options(
            selectinload(CandidateProfile.employment),
            selectinload(CandidateProfile.skills).joinedload(CandidateSkill.skill),
        )
    )
    return db.scalars(stmt).first()


def get_employment(db: Session, profile_id: uuid.UUID, employment_id: uuid.UUID) -> EmploymentHistory | None:
    stmt = select(EmploymentHistory).where(
        EmploymentHistory.id == employment_id, EmploymentHistory.profile_id == profile_id
    )
    return db.scalars(stmt).first()


def get_or_create_skill(db: Session, display_name: str) -> Skill:
    name = " ".join(display_name.lower().split())
    skill = db.scalars(select(Skill).where(Skill.name == name)).first()
    if skill is None:
        skill = Skill(name=name, display_name=display_name.strip())
        db.add(skill)
        db.flush()
    return skill

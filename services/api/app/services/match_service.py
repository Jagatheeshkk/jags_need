from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scoring import DEFAULT_SCORE_WEIGHTS
from app.models import AutomationRule, Job, JobMatch, User
from app.services import profile_service
from app.services.matching import get_engine, inputs_hash


def weights_for(db: Session, user: User) -> dict[str, int]:
    rule = db.scalars(select(AutomationRule).where(AutomationRule.user_id == user.id)).first()
    if rule and rule.score_weights and set(rule.score_weights) == set(DEFAULT_SCORE_WEIGHTS):
        return {k: int(v) for k, v in rule.score_weights.items()}
    return dict(DEFAULT_SCORE_WEIGHTS)


def rescore_all(db: Session, user: User, force: bool = False) -> int:
    """(Re)compute matches for every job whose inputs changed. Returns how many were scored."""
    profile = profile_service.get_or_create(db, user)
    weights = weights_for(db, user)
    current = inputs_hash(profile, weights)
    engine = get_engine()
    existing = {m.job_id: m for m in db.scalars(select(JobMatch).where(JobMatch.user_id == user.id))}
    scored = 0
    for job in db.scalars(select(Job)):
        m = existing.get(job.id)
        up_to_date = (
            m is not None
            and m.breakdown.get("inputs_hash") == current
            and m.breakdown.get("job_updated_at") == job.updated_at.isoformat()
        )
        if up_to_date and not force:
            continue
        r = engine.score(profile, job, weights)
        breakdown = {**r.breakdown(), "job_updated_at": job.updated_at.isoformat()}
        if m is None:
            m = JobMatch(user_id=user.id, job_id=job.id)  # keeps is_saved/feedback defaults
            db.add(m)
        m.score = r.score
        m.breakdown = breakdown
        m.matched_skills = r.matched_skills
        m.missing_skills = r.missing_skills
        m.eligibility = r.eligibility
        m.explanation = r.explanation
        m.engine = r.engine
        m.updated_at = datetime.now(UTC)
        scored += 1
    db.commit()
    return scored

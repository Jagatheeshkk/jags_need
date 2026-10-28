from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import AutomationRule
from app.schemas.settings import AutomationRulesIn, AutomationRulesOut, ReadinessReport
from app.services import audit, readiness, usage

router = APIRouter(prefix="/settings", tags=["settings"])


def _rules(db: DbSession, user: CurrentUser) -> AutomationRule:
    rule = db.scalars(select(AutomationRule).where(AutomationRule.user_id == user.id)).first()
    if rule is None:
        rule = AutomationRule(user_id=user.id, **AutomationRulesIn().model_dump())
        db.add(rule)
        db.commit()
    return rule


@router.get("/automation", response_model=AutomationRulesOut)
def get_automation(user: CurrentUser, db: DbSession) -> AutomationRule:
    return _rules(db, user)


@router.put("/automation", response_model=AutomationRulesOut)
def put_automation(body: AutomationRulesIn, request: Request, user: CurrentUser, db: DbSession) -> AutomationRule:
    rule = _rules(db, user)
    values = body.model_dump(mode="json")
    changed = sorted(k for k, v in values.items() if getattr(rule, k) != v)
    for k, v in values.items():
        setattr(rule, k, v)
    audit.record(
        db,
        "automation_rules.updated",
        user_id=user.id,
        entity_type="automation_rules",
        entity_id=rule.id,
        details={"fields": changed},
        request=request,
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/readiness", response_model=ReadinessReport)
def get_readiness(user: CurrentUser, db: DbSession, settings: AppSettings) -> ReadinessReport:
    return readiness.run(db, settings)


@router.get("/usage")
def get_usage(user: CurrentUser, db: DbSession, settings: AppSettings) -> dict[str, Any]:
    """Database storage used against the free plan's quota, plus row counts."""
    return usage.report(db, settings)

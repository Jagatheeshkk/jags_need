import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import ApprovalRequest, TaskRun
from app.schemas.jobs import TaskRunOut
from app.services import audit, automation, tasks

router = APIRouter(tags=["automation"])


class DecisionOut(BaseModel):
    job_id: str
    title: str
    company: str
    portal: str | None
    score: float | None
    action: Literal["submit", "approval", "skip"]
    reasons: list[str]
    checks: list[dict[str, Any]]


class PreviewOut(BaseModel):
    enabled: bool
    global_pause: bool
    decisions: list[DecisionOut]
    totals: dict[str, int]


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    subject_type: str
    subject_id: uuid.UUID | None
    payload: dict[str, Any]
    status: str
    created_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None


class ApproveIn(BaseModel):
    confirm_reviewed: bool = False
    note: str | None = Field(default=None, max_length=1000)


class RejectIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ApprovalDecisionOut(BaseModel):
    approval: ApprovalOut
    outcome: str


@router.get("/automation/preview", response_model=PreviewOut)
def preview(user: CurrentUser, db: DbSession) -> PreviewOut:
    """Dry run: what the engine would do right now. Creates nothing and submits nothing."""
    rules = automation.get_rules(db, user)
    decisions = automation.preview(db, user)
    totals = {a: sum(1 for d in decisions if d.action == a) for a in ("submit", "approval", "skip")}
    return PreviewOut(
        enabled=rules.enabled,
        global_pause=rules.global_pause,
        totals=totals,
        decisions=[
            DecisionOut(
                job_id=d.job_id,
                title=d.title,
                company=d.company,
                portal=d.portal,
                score=d.score,
                action=d.action,
                reasons=d.reasons,
                checks=[asdict(c) for c in d.checks],
            )
            for d in decisions
        ],
    )


@router.post("/automation/run", response_model=TaskRunOut)
def run(request: Request, user: CurrentUser, db: DbSession) -> TaskRun:
    try:
        result = automation.run(db, user, trigger="manual")
    except tasks.TaskAlreadyRunning as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Automation is already running") from exc
    audit.record(
        db,
        "automation.run",
        user_id=user.id,
        entity_type="task_run",
        entity_id=result.id,
        details={k: result.result.get(k) for k in ("state", "submitted", "approvals_created", "skipped")},
        request=request,
    )
    db.commit()
    return result


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    user: CurrentUser,
    db: DbSession,
    status_filter: Literal["pending", "approved", "rejected", "expired"] | None = Query(None, alias="status"),
) -> list[ApprovalRequest]:
    automation.expire_stale(db, user)
    stmt = select(ApprovalRequest).where(ApprovalRequest.user_id == user.id)
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    return list(db.scalars(stmt.order_by(ApprovalRequest.created_at.desc()).limit(200)))


@router.post("/approvals/{req_id}/approve", response_model=ApprovalDecisionOut)
def approve(
    req_id: uuid.UUID, body: ApproveIn, request: Request, user: CurrentUser, db: DbSession
) -> ApprovalDecisionOut:
    try:
        req, outcome = automation.approve(db, user, req_id, body.confirm_reviewed, body.note)
    except automation.ApprovalError as exc:
        raise HTTPException(exc.status, detail=str(exc)) from exc
    audit.record(
        db, "approval.approved", user_id=user.id, entity_type="approval_request", entity_id=req.id, request=request
    )
    db.commit()
    return ApprovalDecisionOut(approval=ApprovalOut.model_validate(req), outcome=outcome)


@router.post("/approvals/{req_id}/reject", response_model=ApprovalDecisionOut)
def reject(
    req_id: uuid.UUID, body: RejectIn, request: Request, user: CurrentUser, db: DbSession
) -> ApprovalDecisionOut:
    try:
        req = automation.reject(db, user, req_id, body.note)
    except automation.ApprovalError as exc:
        raise HTTPException(exc.status, detail=str(exc)) from exc
    audit.record(
        db, "approval.rejected", user_id=user.id, entity_type="approval_request", entity_id=req.id, request=request
    )
    db.commit()
    return ApprovalDecisionOut(approval=ApprovalOut.model_validate(req), outcome="Rejected. Nothing was submitted.")

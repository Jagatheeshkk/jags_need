"""Portal profile sync.

No real portal permits automated profile updates (Phase 5 verification), so for them the app
generates the text, shows what changed since the last confirmed sync, and records that the user
updated the portal themselves. Only the mock connector can apply an update automatically, and
that result is simulated and labelled as such.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ManualPortalConnector, PortalConnector
from app.connectors.registry import get_connector
from app.models import CandidateProfile, EmploymentHistory, Portal, ProfileSyncRun, User
from app.services import portal_service, profile_service


class SyncError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _connector(code: str) -> PortalConnector:
    c = get_connector(code)
    if c is None:
        raise SyncError("Unknown portal", 404)
    return c


def _role_block(e: EmploymentHistory) -> str:
    end = "Present" if e.is_current else (e.end_date.strftime("%b %Y") if e.end_date else "")
    lines = [
        f"{e.title} — {e.company}" + (f", {e.location}" if e.location else ""),
        f"{e.start_date.strftime('%b %Y')} – {end}",
        e.description or "",
        *[f"• {a}" for a in e.achievements or []],
    ]
    return "\n".join(line for line in lines if line)


def build_content(profile: CandidateProfile) -> list[dict[str, Any]]:
    """Portal-ready text for each profile section, from profile facts only."""
    roles = sorted(profile.employment, key=lambda e: (e.is_current, e.start_date), reverse=True)
    experience = "\n\n".join(_role_block(e) for e in roles)
    skills = [cs.skill.display_name for cs in sorted(profile.skills, key=lambda s: (not s.is_primary, s.skill.name))]
    education = "\n".join(
        f"{ed.get('degree')}, {ed.get('institution')}" + (f" ({ed['end_year']})" if ed.get("end_year") else "")
        for ed in profile.education or []
    )
    certs = "\n".join(c.get("name", "") for c in profile.certifications or [])
    prefs = "; ".join(
        filter(
            None,
            [
                f"Roles: {', '.join(profile.preferred_roles)}" if profile.preferred_roles else "",
                f"Locations: {', '.join(profile.preferred_locations)}" if profile.preferred_locations else "",
                f"Work arrangement: {profile.work_arrangement}" if profile.work_arrangement != "any" else "",
                f"Notice period: {profile.notice_period_days} days" if profile.notice_period_days is not None else "",
            ],
        )
    )
    fields = [
        ("headline", "Headline", profile.headline or ""),
        ("summary", "Summary / About", profile.summary or ""),
        ("skills", "Skills", ", ".join(skills)),
        ("experience", "Experience", experience),
        ("education", "Education", education),
        ("certifications", "Certifications", certs),
        ("preferences", "Job preferences", prefs),
    ]
    # Character counts only: portals' own editors enforce their limits (not published officially).
    return [{"key": k, "label": label, "value": v, "chars": len(v)} for k, label, v in fields]


def _hash(fields: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps([[f["key"], f["value"]] for f in fields]).encode()).hexdigest()


def last_completed(db: Session, user: User, portal_id: Any) -> ProfileSyncRun | None:
    stmt = (
        select(ProfileSyncRun)
        .where(
            ProfileSyncRun.user_id == user.id,
            ProfileSyncRun.portal_id == portal_id,
            ProfileSyncRun.status.in_(["manual_completed", "succeeded"]),
        )
        .order_by(ProfileSyncRun.finished_at.desc())
    )
    return db.scalars(stmt).first()


def preview(db: Session, user: User, code: str) -> dict[str, Any]:
    connector = _connector(code)
    portal = portal_service.ensure_portals(db)[code]
    fields = build_content(profile_service.get_or_create(db, user))
    last = last_completed(db, user, portal.id)
    before = {f["key"]: f["value"] for f in (last.preview.get("fields", []) if last else [])}
    for f in fields:
        f["changed"] = last is None or before.get(f["key"]) != f["value"]
    caps = connector.get_capabilities()
    return {
        "portal": code,
        "portal_name": connector.name,
        "automated": caps.update_profile,
        "simulated": caps.mode.value == "mock",
        "fields": fields,
        "changed": [f["key"] for f in fields if f["changed"]],
        "last_synced_at": last.finished_at if last else None,
        "content_hash": _hash(fields),
        "instructions": _instructions(connector),
    }


def _instructions(connector: PortalConnector) -> list[str]:
    if not isinstance(connector, ManualPortalConnector):
        return ["The mock portal accepts simulated updates; nothing leaves this app."]
    return [
        f"Open {connector.name} in your browser and sign in ({connector.base_url}).",
        "Open your profile editor.",
        "Copy each changed section below into the matching field; the portal's editor enforces its own limits.",
        "Save on the portal, then come back and confirm here.",
    ]


def prepare(db: Session, user: User, code: str) -> tuple[ProfileSyncRun, bool]:
    """Record a sync for the current content. Same content twice returns the same run."""
    p = preview(db, user, code)
    portal = portal_service.ensure_portals(db)[code]
    # Fixed length (fits the 100-char column): same user, portal and content -> same key.
    key = "profile_sync:" + hashlib.sha256(f"{user.id}:{code}:{p['content_hash']}".encode()).hexdigest()
    existing = db.scalars(select(ProfileSyncRun).where(ProfileSyncRun.idempotency_key == key)).first()
    if existing:
        return existing, False
    run = ProfileSyncRun(
        user_id=user.id,
        portal_id=portal.id,
        idempotency_key=key,
        status="pending" if p["automated"] else "manual_required",
        preview={k: p[k] for k in ("fields", "changed", "instructions", "content_hash")},
        attempts=0,
    )
    db.add(run)
    db.commit()
    return run, True


def _owned_run(db: Session, user: User, run_id: Any) -> ProfileSyncRun:
    run = db.get(ProfileSyncRun, run_id)
    if run is None or run.user_id != user.id:
        raise SyncError("Sync run not found", 404)
    return run


def confirm_manual(db: Session, user: User, run_id: Any, confirm_updated: bool) -> ProfileSyncRun:
    run = _owned_run(db, user, run_id)
    if run.status != "manual_required":
        raise SyncError(f"This sync is {run.status}.", 409)
    if not confirm_updated:
        raise SyncError("Confirm that you saved these changes on the portal yourself (confirm_updated).")
    run.status = "manual_completed"
    run.finished_at = datetime.now(UTC)
    run.result = {"confirmed_by_user": True, "automated": False, "fields": run.preview.get("changed", [])}
    db.commit()
    return run


def run_automated(db: Session, user: User, run_id: Any) -> ProfileSyncRun:
    """Only for connectors whose update_profile capability is permitted (the mock connector)."""
    run = _owned_run(db, user, run_id)
    if run.status not in {"pending", "failed"}:
        raise SyncError(f"This sync is {run.status}.", 409)
    portal = db.get(Portal, run.portal_id)
    connector = _connector(portal.code if portal else "")
    if not connector.get_capabilities().update_profile:
        raise SyncError("This portal does not permit automated profile updates.", 409)
    run.attempts += 1
    result = connector.update_profile({f["key"]: f["value"] for f in run.preview.get("fields", [])})
    run.status = "succeeded" if result.status == "succeeded" else "failed"
    run.finished_at = datetime.now(UTC)
    run.result = {"automated": True, "simulated": result.simulated, "message": result.message}
    db.commit()
    return run


def cancel(db: Session, user: User, run_id: Any) -> ProfileSyncRun:
    run = _owned_run(db, user, run_id)
    if run.status not in {"manual_required", "pending", "failed"}:
        raise SyncError(f"This sync is {run.status}.", 409)
    run.status = "cancelled"
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run


def history(db: Session, user: User, code: str | None = None) -> list[ProfileSyncRun]:
    stmt = select(ProfileSyncRun).where(ProfileSyncRun.user_id == user.id)
    if code:
        _connector(code)
        stmt = stmt.where(ProfileSyncRun.portal_id == portal_service.ensure_portals(db)[code].id)
    return list(db.scalars(stmt.order_by(ProfileSyncRun.created_at.desc()).limit(100)))

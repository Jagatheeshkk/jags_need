from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.base import Capabilities, IntegrationMode
from app.connectors.registry import all_connectors, get_connector
from app.models import Portal, PortalConnection, User


class PortalOut(BaseModel):
    code: str
    name: str
    base_url: str | None
    status: str
    capabilities: Capabilities
    last_checked_at: datetime | None
    last_error: str | None


def ensure_portals(db: Session) -> dict[str, Portal]:
    """Idempotently create a portals row for each registered connector."""
    existing = {p.code: p for p in db.scalars(select(Portal))}
    for c in all_connectors():
        caps = c.get_capabilities()
        portal = existing.get(c.code)
        if portal is None:
            portal = Portal(
                code=c.code, name=c.name, base_url=c.base_url, integration_mode=caps.mode.value, notes=caps.notes
            )
            db.add(portal)
            existing[c.code] = portal
        else:
            portal.integration_mode = caps.mode.value
            portal.notes = caps.notes
    try:
        db.commit()
    except IntegrityError:  # concurrent first request created them
        db.rollback()
        existing = {p.code: p for p in db.scalars(select(Portal))}
    return existing


def _default_status(mode: IntegrationMode) -> str:
    return "unsupported" if mode == IntegrationMode.UNVERIFIED else "not_connected"


def list_for_user(db: Session, user: User) -> list[PortalOut]:
    portals = ensure_portals(db)
    connections = {
        c.portal_id: c for c in db.scalars(select(PortalConnection).where(PortalConnection.user_id == user.id))
    }
    out = []
    for c in all_connectors():
        portal = portals[c.code]
        caps = c.get_capabilities()
        conn = connections.get(portal.id)
        out.append(
            PortalOut(
                code=c.code,
                name=c.name,
                base_url=c.base_url,
                status=conn.status if conn else _default_status(caps.mode),
                capabilities=caps,
                last_checked_at=conn.last_checked_at if conn else None,
                last_error=conn.last_error if conn else None,
            )
        )
    return out


def check_connection(db: Session, user: User, code: str) -> PortalOut | None:
    """Re-evaluate a portal's state. Real portals are reported as unsupported until verified."""
    connector = get_connector(code)
    if connector is None:
        return None
    portals = ensure_portals(db)
    portal = portals[code]
    conn = db.scalars(
        select(PortalConnection).where(PortalConnection.user_id == user.id, PortalConnection.portal_id == portal.id)
    ).first()
    if conn is None:
        conn = PortalConnection(user_id=user.id, portal_id=portal.id)
        db.add(conn)
    mode = connector.get_capabilities().mode
    conn.status = "connected" if mode == IntegrationMode.MOCK else _default_status(mode)
    conn.auth_method = "none" if mode == IntegrationMode.MOCK else None
    conn.last_checked_at = datetime.now(UTC)
    conn.last_error = None
    db.commit()
    return next(p for p in list_for_user(db, user) if p.code == code)

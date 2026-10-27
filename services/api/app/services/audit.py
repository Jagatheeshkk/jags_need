import hashlib
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditLog


def _ip_hash(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    # Store a keyed hash, not the raw IP address (minimal personal data).
    salt = get_settings().secret_key
    return hashlib.sha256(f"{salt}:{request.client.host}".encode()).hexdigest()[:32]


def record(
    db: Session,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Add an audit event to the current transaction (the caller commits)."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details or {},
            ip_hash=_ip_hash(request),
        )
    )

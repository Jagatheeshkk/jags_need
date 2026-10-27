import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk


class Portal(UUIDPk, Timestamps, Base):
    __tablename__ = "portals"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(300))
    # mock | unverified | manual | api  (see connectors.base.IntegrationMode)
    integration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="unverified")
    notes: Mapped[str | None] = mapped_column(Text)


class PortalConnection(UUIDPk, Timestamps, Base):
    __tablename__ = "portal_connections"
    __table_args__ = (UniqueConstraint("user_id", "portal_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    portal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("portals.id", ondelete="CASCADE"), nullable=False)
    # connected | not_connected | unsupported | needs_user_action | sleeping | rate_limited | failed
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_connected")
    auth_method: Mapped[str | None] = mapped_column(String(30))
    # Name of an environment variable / secret holding credentials. Never the secret itself.
    credential_ref: Mapped[str | None] = mapped_column(String(100))
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    portal: Mapped[Portal] = relationship(lazy="joined")

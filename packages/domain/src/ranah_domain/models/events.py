import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import ProjectEventActorType
from ranah_domain.mixins import UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class ProjectEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail. Never updated or deleted by application code."""

    __tablename__ = "project_events"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor_type: Mapped[ProjectEventActorType] = mapped_column(enum_column(ProjectEventActorType))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class UsageEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "usage_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(50))
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

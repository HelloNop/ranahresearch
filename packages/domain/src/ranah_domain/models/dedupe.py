import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import DuplicateDecisionType, DuplicateGroupStatus, DuplicateGroupType
from ranah_domain.mixins import UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class DuplicateGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "duplicate_groups"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    duplicate_type: Mapped[DuplicateGroupType] = mapped_column(enum_column(DuplicateGroupType))
    status: Mapped[DuplicateGroupStatus] = mapped_column(
        enum_column(DuplicateGroupStatus), default=DuplicateGroupStatus.OPEN
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DuplicateMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "duplicate_members"

    duplicate_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signals: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("duplicate_group_id", "work_id"),)


class DuplicateDecision(UUIDPrimaryKeyMixin, Base):
    """No destructive deletion: duplicates are merged/kept by decision, not removed."""

    __tablename__ = "duplicate_decisions"

    duplicate_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"), index=True
    )
    canonical_work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_records.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[DuplicateDecisionType] = mapped_column(enum_column(DuplicateDecisionType))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

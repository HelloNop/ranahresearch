import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import (
    StudyLinkDecisionType,
    StudyStatus,
    StudyType,
    StudyWorkRelationship,
)
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class Study(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The underlying research study, which may be reported by several works.

    Distinct from WorkRecord: linking reports to one study is not deduplication,
    and never removes a publication (docs/DATA_MODEL.md #30).
    """

    __tablename__ = "studies"
    __table_args__ = (UniqueConstraint("project_id", "study_label"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    study_label: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(Text)
    study_type: Mapped[StudyType] = mapped_column(enum_column(StudyType), default=StudyType.OTHER)
    status: Mapped[StudyStatus] = mapped_column(
        enum_column(StudyStatus), default=StudyStatus.CANDIDATE
    )
    country: Mapped[str | None] = mapped_column(String(200), nullable=True)
    setting: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recruitment_period: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registration_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # Merging supersedes rather than deletes, so link history keeps its referent.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("studies.id", ondelete="SET NULL"), nullable=True
    )


class StudyWork(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "study_works"
    __table_args__ = (UniqueConstraint("study_id", "work_id"),)

    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[StudyWorkRelationship] = mapped_column(
        enum_column(StudyWorkRelationship)
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    linked_by: Mapped[str] = mapped_column(String(100))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudyLinkDecision(UUIDPrimaryKeyMixin, Base):
    """Immutable record of every link judgement, including the ones that decided
    two reports are separate studies."""

    __tablename__ = "study_link_decisions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    candidate_work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), nullable=True
    )
    study_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), nullable=True
    )
    decision: Mapped[StudyLinkDecisionType] = mapped_column(enum_column(StudyLinkDecisionType))
    relationship_type: Mapped[StudyWorkRelationship | None] = mapped_column(
        enum_column(StudyWorkRelationship), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(10))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

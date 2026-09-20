import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.mixins import UUIDPrimaryKeyMixin


class ReviewProtocol(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "review_protocols"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_projects.id"), index=True)
    research_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_plans.id"))
    framework_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_frameworks.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PROPOSED")
    background: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    research_question: Mapped[str] = mapped_column(Text)
    review_type: Mapped[str] = mapped_column(String(50))
    screening_strategy: Mapped[str] = mapped_column(Text)
    extraction_strategy: Mapped[str] = mapped_column(Text)
    synthesis_strategy: Mapped[str] = mapped_column(Text)
    risk_of_bias_plan: Mapped[str] = mapped_column(Text)
    meta_analysis_plan: Mapped[str] = mapped_column(Text)
    meta_analysis_planned: Mapped[bool]
    information_sources: Mapped[list[str]] = mapped_column(JSONB)
    assumptions: Mapped[list[str]] = mapped_column(JSONB)
    uncertainties: Mapped[list[str]] = mapped_column(JSONB)
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EligibilityCriterion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eligibility_criteria"
    protocol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_protocols.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(50))
    operator: Mapped[str] = mapped_column(String(20))
    value: Mapped[Any] = mapped_column(JSONB)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProtocolAmendment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "protocol_amendments"
    protocol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_protocols.id"), index=True)
    from_version: Mapped[int]
    to_version: Mapped[int]
    field_path: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[Any] = mapped_column(JSONB)
    new_value: Mapped[Any] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(50))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScreeningDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "screening_decisions"
    __table_args__ = (
        Index(
            "screening_ai_once",
            "protocol_id",
            "work_id",
            "stage",
            unique=True,
            postgresql_where=text("reviewer_type = 'AI'"),
        ),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_projects.id"), index=True)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_records.id"), index=True)
    study_id: Mapped[uuid.UUID | None]
    protocol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_protocols.id"), index=True)
    protocol_version: Mapped[int]
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(30))
    decision: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str | None] = mapped_column(String(50))
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    reviewer_type: Mapped[str] = mapped_column(String(10))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    criterion_assessments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    evidence_spans: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

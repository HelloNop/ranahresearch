import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.mixins import UUIDPrimaryKeyMixin


class RiskOfBiasAssessment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "risk_of_bias_assessments"
    __table_args__ = (UniqueConstraint("study_id", "version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(30))
    tool_version: Mapped[str] = mapped_column(String(30))
    overall_judgement: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class RiskOfBiasDomain(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "risk_of_bias_domains"
    __table_args__ = (UniqueConstraint("assessment_id", "domain_code"),)

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_of_bias_assessments.id", ondelete="CASCADE"), index=True
    )
    domain_code: Mapped[str] = mapped_column(String(50))
    judgement: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(Text)
    supporting_evidence: Mapped[str] = mapped_column(Text)
    work_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_records.id"), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

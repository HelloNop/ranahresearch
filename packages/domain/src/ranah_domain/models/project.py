import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import (
    AutonomyMode,
    ProjectStatus,
    ResearchFrameworkType,
    ResearchMethod,
    ResearchPlanStatus,
)
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class ResearchProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500))
    working_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_method: Mapped[ResearchMethod | None] = mapped_column(
        enum_column(ResearchMethod), nullable=True
    )
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus), default=ProjectStatus.IDEA, index=True
    )
    language: Mapped[str] = mapped_column(String(10), default="en")
    # TargetJournal is out of scope for this slice; kept as an unconstrained reference.
    target_journal_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    autonomy_mode: Mapped[AutonomyMode] = mapped_column(
        enum_column(AutonomyMode), default=AutonomyMode.BALANCED
    )


class ResearchIdea(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_ideas"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(50), default="USER")
    # Conversation/Message are out of scope for this slice.
    conversation_message_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchPlan(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_plans"
    content: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    research_idea_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_ideas.id"), nullable=True
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[ResearchPlanStatus] = mapped_column(
        enum_column(ResearchPlanStatus), default=ResearchPlanStatus.DRAFT
    )
    provisional_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_method: Mapped[ResearchMethod | None] = mapped_column(
        enum_column(ResearchMethod), nullable=True
    )
    recommended_framework: Mapped[ResearchFrameworkType | None] = mapped_column(
        enum_column(ResearchFrameworkType), nullable=True
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_research_plans_project_version", "project_id", "version"),)


class ResearchQuestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_questions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    research_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_plans.id", ondelete="CASCADE"), index=True
    )
    question_type: Mapped[str] = mapped_column(String(50))
    question_text: Mapped[str] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchFramework(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_frameworks"
    research_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_plans.id"), nullable=True, unique=True
    )
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    framework_type: Mapped[ResearchFrameworkType] = mapped_column(
        enum_column(ResearchFrameworkType)
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    structured_elements: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

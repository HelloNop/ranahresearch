import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import AgentDefinitionStatus, AgentRunStatus
from ranah_domain.mixins import UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class AgentDefinition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_definitions"

    name: Mapped[str] = mapped_column(String(200), index=True)
    version: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[AgentDefinitionStatus] = mapped_column(
        enum_column(AgentDefinitionStatus), default=AgentDefinitionStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("name", "version"),)


class AgentRun(UUIDPrimaryKeyMixin, Base):
    """Every run is reproducible from here: definition, prompt version, model, and I/O metadata."""

    __tablename__ = "agent_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_definitions.id", ondelete="RESTRICT"), index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus), default=AgentRunStatus.RUNNING, index=True
    )
    model_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    output_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

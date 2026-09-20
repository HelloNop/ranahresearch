import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import WorkflowRunStatus
from ranah_domain.mixins import UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class WorkflowRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workflow_runs"
    stage: Mapped[str] = mapped_column(String(100), default="PENDING")
    details: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    temporal_workflow_id: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    workflow_type: Mapped[str] = mapped_column(String(200))
    status: Mapped[WorkflowRunStatus] = mapped_column(
        enum_column(WorkflowRunStatus), default=WorkflowRunStatus.RUNNING, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

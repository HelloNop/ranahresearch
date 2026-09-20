import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import SearchArtifactStatus, SearchRunStatus
from ranah_domain.mixins import UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class SearchStrategy(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "search_strategies"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    # ReviewProtocol is out of scope for this slice; kept as an unconstrained reference.
    protocol_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[SearchArtifactStatus] = mapped_column(
        enum_column(SearchArtifactStatus), default=SearchArtifactStatus.DRAFT
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SearchQuery(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "search_queries"

    search_strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_strategies.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    query_text: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[SearchArtifactStatus] = mapped_column(
        enum_column(SearchArtifactStatus), default=SearchArtifactStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "search_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    search_query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_queries.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    executed_query: Mapped[str] = mapped_column(Text)
    executed_filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_count_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_count_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[SearchRunStatus] = mapped_column(
        enum_column(SearchRunStatus), default=SearchRunStatus.PENDING, index=True
    )
    provider_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "search_results"

    search_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), index=True
    )
    provider_record_id: Mapped[str] = mapped_column(String(300))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    normalized_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("search_run_id", "provider_record_id"),)

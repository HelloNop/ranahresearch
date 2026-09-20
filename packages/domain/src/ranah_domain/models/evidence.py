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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import (
    EvidenceStatus,
    EvidenceValueType,
    EvidenceVerificationStatus,
    ExtractionSchemaStatus,
)
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class ExtractionSchema(UUIDPrimaryKeyMixin, Base):
    """Project-specific extraction form, derived from the protocol. There is no
    universal form: what must be extracted depends on the research question."""

    __tablename__ = "extraction_schemas"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    protocol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_protocols.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[ExtractionSchemaStatus] = mapped_column(
        enum_column(ExtractionSchemaStatus), default=ExtractionSchemaStatus.DRAFT
    )
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One extracted field value for one study, traceable to its source.

    A correction never overwrites: the prior row is marked SUPERSEDED and points
    at its replacement, so the AI's original extraction stays inspectable.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("evidence_study_field", "study_id", "field_name"),
        Index("evidence_current", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_records.id", ondelete="SET NULL"), nullable=True
    )
    extraction_schema_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_schemas.id"), nullable=True
    )
    evidence_type: Mapped[str] = mapped_column(String(30))
    field_name: Mapped[str] = mapped_column(String(100))
    value_json: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    value_type: Mapped[EvidenceValueType] = mapped_column(enum_column(EvidenceValueType))
    derivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_status: Mapped[EvidenceVerificationStatus] = mapped_column(
        enum_column(EvidenceVerificationStatus), default=EvidenceVerificationStatus.UNVERIFIED
    )
    status: Mapped[EvidenceStatus] = mapped_column(
        enum_column(EvidenceStatus), default=EvidenceStatus.CURRENT
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True
    )
    extractor_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    entered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvidenceProvenance(UUIDPrimaryKeyMixin, Base):
    """Where a value came from: document, chunk, page, section, and the quote."""

    __tablename__ = "evidence_provenance"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    parsed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parsed_documents.id", ondelete="SET NULL"), nullable=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_records.id", ondelete="SET NULL"), nullable=True
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quote_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceVerification(UUIDPrimaryKeyMixin, Base):
    """Immutable verification event: deterministic check, reviewer agent, or human."""

    __tablename__ = "evidence_verifications"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    verification_method: Mapped[str] = mapped_column(String(50))
    status: Mapped[EvidenceVerificationStatus] = mapped_column(
        enum_column(EvidenceVerificationStatus)
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class StudyCharacteristic(UUIDPrimaryKeyMixin, Base):
    """Study-level summary of an extracted dimension, pointing at its evidence."""

    __tablename__ = "study_characteristics"
    __table_args__ = (UniqueConstraint("study_id", "dimension"),)

    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(50))
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

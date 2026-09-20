import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import WorkIdentifierType, WorkVerificationStatus, WorkVerificationType
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class WorkRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Canonical publication-level record. Not a Study, an Evidence item, or a Claim."""

    __tablename__ = "work_records"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    doi: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publication_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    journal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    volume: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(300), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    open_access_status: Mapped[str | None] = mapped_column(String(50), nullable=True)


class WorkIdentifier(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "work_identifiers"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    identifier_type: Mapped[WorkIdentifierType] = mapped_column(enum_column(WorkIdentifierType))
    identifier: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (UniqueConstraint("provider", "identifier"),)


class WorkMetadataObservation(UUIDPrimaryKeyMixin, Base):
    """Preserves per-provider metadata as reported, including conflicts between providers."""

    __tablename__ = "work_metadata_observations"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    field_value: Mapped[dict[str, object]] = mapped_column(JSONB)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkVerification(UUIDPrimaryKeyMixin, Base):
    """Identity confidence only. Never conflated with SLR eligibility."""

    __tablename__ = "work_verifications"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    verification_type: Mapped[WorkVerificationType] = mapped_column(
        enum_column(WorkVerificationType)
    )
    status: Mapped[WorkVerificationStatus] = mapped_column(enum_column(WorkVerificationStatus))
    verified_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

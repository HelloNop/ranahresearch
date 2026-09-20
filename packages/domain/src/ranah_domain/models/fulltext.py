import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
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
    FullTextAcquisitionStatus,
    FullTextAssetStatus,
    FullTextSourceType,
)
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class FullTextAcquisition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What retrieval actually achieved for one work. Separate from FullTextAsset
    because "we looked and found nothing" is a fact worth persisting, and an
    asset row without bytes would be a lie."""

    __tablename__ = "full_text_acquisitions"
    __table_args__ = (UniqueConstraint("project_id", "work_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[FullTextAcquisitionStatus] = mapped_column(
        enum_column(FullTextAcquisitionStatus), default=FullTextAcquisitionStatus.NOT_REQUESTED
    )
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FullTextAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One stored full-text file. Content-addressed per work: re-uploading the
    same bytes for the same work reuses this row instead of storing another blob."""

    __tablename__ = "full_text_assets"
    __table_args__ = (UniqueConstraint("work_id", "sha256"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[FullTextSourceType] = mapped_column(enum_column(FullTextSourceType))
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[FullTextAssetStatus] = mapped_column(
        enum_column(FullTextAssetStatus), default=FullTextAssetStatus.AVAILABLE
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    license_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ParsedDocument(UUIDPrimaryKeyMixin, Base):
    """Structured representation of one asset, with the parser that produced it."""

    __tablename__ = "parsed_documents"

    full_text_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("full_text_assets.id", ondelete="CASCADE"), index=True
    )
    parser_name: Mapped[str] = mapped_column(String(100))
    parser_version: Mapped[str] = mapped_column(String(50))
    page_count: Mapped[int] = mapped_column(Integer)
    structure: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="PARSED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    """Retrieval unit that still answers "which page and section is this from?"."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "chunk_index"),
        Index("document_chunk_section", "parsed_document_id", "section_type"),
    )

    parsed_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parsed_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    section_path: Mapped[str] = mapped_column(String(500))
    section_type: Mapped[str] = mapped_column(String(30))
    heading_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

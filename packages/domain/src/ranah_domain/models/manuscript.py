import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ranah_domain.db import Base
from ranah_domain.enums import (
    CitationStyle,
    ClaimBasis,
    ClaimStatus,
    ClaimType,
    ClaimVerificationStatus,
    ConfidenceLevel,
    EvidenceRelationship,
    ExportFormat,
    ExportStatus,
    GapType,
    ManuscriptStatus,
    ManuscriptVersionStatus,
    ReviewerType,
    ReviewIssueStatus,
    ReviewSeverity,
    RevisionTaskStatus,
    SectionStatus,
    SectionType,
    SynthesisMethod,
    SynthesisStatus,
)
from ranah_domain.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from ranah_domain.types import enum_column


class EvidenceSynthesis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_syntheses"
    __table_args__ = (UniqueConstraint("project_id", "research_question_id", "version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    protocol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("review_protocols.id", ondelete="SET NULL"), nullable=True
    )
    research_question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_questions.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[SynthesisStatus] = mapped_column(
        enum_column(SynthesisStatus), default=SynthesisStatus.DRAFT
    )
    method: Mapped[SynthesisMethod] = mapped_column(enum_column(SynthesisMethod))
    limitations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence_notes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )


class SynthesisTheme(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "synthesis_themes"

    synthesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_syntheses.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))
    position: Mapped[int] = mapped_column(Integer, default=0)


class SynthesisFinding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "synthesis_findings"

    synthesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_syntheses.id", ondelete="CASCADE"), index=True
    )
    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("synthesis_themes.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))
    position: Mapped[int] = mapped_column(Integer, default=0)


class SynthesisContradiction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "synthesis_contradictions"

    synthesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_syntheses.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))


class ResearchGap(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_gaps"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    synthesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_syntheses.id", ondelete="CASCADE"), index=True
    )
    gap_type: Mapped[GapType] = mapped_column(enum_column(GapType))
    description: Mapped[str] = mapped_column(Text)
    supporting_observation: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    confidence: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))


class SynthesisEvidenceLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "synthesis_evidence_links"
    __table_args__ = (UniqueConstraint("artifact_type", "artifact_id", "evidence_id"),)

    synthesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_syntheses.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(30))
    artifact_id: Mapped[uuid.UUID] = mapped_column(index=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[EvidenceRelationship] = mapped_column(enum_column(EvidenceRelationship))


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    source_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("synthesis_findings.id", ondelete="SET NULL"), nullable=True
    )
    claim_type: Mapped[ClaimType] = mapped_column(enum_column(ClaimType))
    basis: Mapped[ClaimBasis] = mapped_column(enum_column(ClaimBasis))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[ClaimStatus] = mapped_column(
        enum_column(ClaimStatus), default=ClaimStatus.CANDIDATE
    )
    confidence: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))
    created_by: Mapped[str] = mapped_column(String(20))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )


class ClaimEvidenceLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (UniqueConstraint("claim_id", "evidence_id", "relationship"),)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[EvidenceRelationship] = mapped_column(enum_column(EvidenceRelationship))
    strength: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimStudyLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "claim_study_links"
    __table_args__ = (UniqueConstraint("claim_id", "study_id", "relationship"),)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[EvidenceRelationship] = mapped_column(enum_column(EvidenceRelationship))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimVerification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "claim_verifications"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ClaimVerificationStatus] = mapped_column(enum_column(ClaimVerificationStatus))
    reason: Mapped[str] = mapped_column(Text)
    recommended_qualification: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[ConfidenceLevel] = mapped_column(enum_column(ConfidenceLevel))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TargetJournal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "target_journals"

    name: Mapped[str] = mapped_column(String(500))
    requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ManuscriptPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manuscript_plans"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    proposed_title: Mapped[str] = mapped_column(String(500))
    article_type: Mapped[str] = mapped_column(String(50), default="REVIEW_ARTICLE")
    target_journal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("target_journals.id", ondelete="SET NULL"), nullable=True
    )
    word_budget: Mapped[int] = mapped_column(Integer)
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )


class ManuscriptSectionPlan(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "manuscript_section_plans"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_plans.id", ondelete="CASCADE"), index=True
    )
    section_type: Mapped[SectionType] = mapped_column(enum_column(SectionType))
    heading: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer)
    objectives: Mapped[list[str]] = mapped_column(JSONB, default=list)
    evidence_requirements: Mapped[list[str]] = mapped_column(JSONB, default=list)
    citation_requirements: Mapped[list[str]] = mapped_column(JSONB, default=list)
    target_words: Mapped[int] = mapped_column(Integer)


class SectionPlanClaim(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "section_plan_claims"
    __table_args__ = (UniqueConstraint("section_plan_id", "claim_id"),)

    section_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_section_plans.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )


class Manuscript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manuscripts"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscript_plans.id"))
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[ManuscriptStatus] = mapped_column(
        enum_column(ManuscriptStatus), default=ManuscriptStatus.DRAFT
    )
    article_type: Mapped[str] = mapped_column(String(50))
    target_journal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("target_journals.id", ondelete="SET NULL"), nullable=True
    )
    citation_style: Mapped[CitationStyle] = mapped_column(
        enum_column(CitationStyle), default=CitationStyle.APA_7
    )
    authors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "manuscript_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_manuscripts_current_version",
        ),
        nullable=True,
    )


class ManuscriptVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "manuscript_versions"
    __table_args__ = (UniqueConstraint("manuscript_id", "version"),)

    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[ManuscriptVersionStatus] = mapped_column(
        enum_column(ManuscriptVersionStatus), default=ManuscriptVersionStatus.DRAFT
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="SET NULL"), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(20), default="AGENT")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManuscriptSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manuscript_sections"
    __table_args__ = (UniqueConstraint("manuscript_version_id", "position"),)

    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscript_sections.id", ondelete="CASCADE"), nullable=True
    )
    section_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscript_section_plans.id", ondelete="SET NULL"), nullable=True
    )
    section_type: Mapped[SectionType] = mapped_column(enum_column(SectionType))
    heading: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[SectionStatus] = mapped_column(
        enum_column(SectionStatus), default=SectionStatus.PLANNED
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )


class ManuscriptClaimLocation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "manuscript_claim_locations"

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_sections.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    exact_text: Mapped[str] = mapped_column(Text)


class ManuscriptCitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "manuscript_citations"

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_sections.id", ondelete="CASCADE"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_records.id", ondelete="RESTRICT"), index=True
    )
    token: Mapped[str] = mapped_column(String(80))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)


class ReviewReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "review_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True
    )
    reviewer_type: Mapped[ReviewerType] = mapped_column(enum_column(ReviewerType))
    summary: Mapped[str] = mapped_column(Text, default="")
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewIssue(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "review_issues"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id", ondelete="CASCADE"), index=True
    )
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscript_sections.id", ondelete="CASCADE"), nullable=True
    )
    reviewer_type: Mapped[ReviewerType] = mapped_column(enum_column(ReviewerType))
    severity: Mapped[ReviewSeverity] = mapped_column(enum_column(ReviewSeverity))
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[ReviewIssueStatus] = mapped_column(
        enum_column(ReviewIssueStatus), default=ReviewIssueStatus.OPEN
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RevisionTask(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "revision_tasks"

    review_issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_issues.id", ondelete="CASCADE"), index=True
    )
    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscript_sections.id", ondelete="CASCADE"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(50))
    instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[RevisionTaskStatus] = mapped_column(
        enum_column(RevisionTaskStatus), default=RevisionTaskStatus.OPEN
    )
    assigned_agent: Mapped[str] = mapped_column(String(100), default="revision_agent")
    revision_round: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ManuscriptExport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "manuscript_exports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), index=True
    )
    manuscript_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscript_versions.id", ondelete="CASCADE"), index=True
    )
    citation_style: Mapped[CitationStyle] = mapped_column(enum_column(CitationStyle))
    export_format: Mapped[ExportFormat] = mapped_column(enum_column(ExportFormat))
    status: Mapped[ExportStatus] = mapped_column(
        enum_column(ExportStatus), default=ExportStatus.PENDING
    )
    exporter_version: Mapped[str] = mapped_column(String(30), default="1")
    artifact_location: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

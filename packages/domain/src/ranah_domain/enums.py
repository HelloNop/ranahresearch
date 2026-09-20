"""Domain enums for the EPIC-003 MVP slice. See docs/DATA_MODEL.md for the full vocabulary."""

import enum


class ProjectMemberRole(enum.StrEnum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class ResearchMethod(enum.StrEnum):
    NARRATIVE_REVIEW = "NARRATIVE_REVIEW"
    SCOPING_REVIEW = "SCOPING_REVIEW"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    SYSTEMATIC_REVIEW_META_ANALYSIS = "SYSTEMATIC_REVIEW_META_ANALYSIS"


class ProjectStatus(enum.StrEnum):
    IDEA = "IDEA"
    EXPLORATION = "EXPLORATION"
    PLANNING = "PLANNING"
    PROTOCOL = "PROTOCOL"
    SEARCHING = "SEARCHING"
    SCREENING = "SCREENING"
    EXTRACTION = "EXTRACTION"
    SYNTHESIS = "SYNTHESIS"
    ANALYSIS = "ANALYSIS"
    WRITING = "WRITING"
    REVIEW = "REVIEW"
    REVISION = "REVISION"
    AUTHOR_REVIEW = "AUTHOR_REVIEW"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class AutonomyMode(enum.StrEnum):
    GUIDED = "GUIDED"
    BALANCED = "BALANCED"
    AUTONOMOUS = "AUTONOMOUS"


class ResearchPlanStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class ResearchFrameworkType(enum.StrEnum):
    PICO = "PICO"
    PICOS = "PICOS"
    PCC = "PCC"
    SPIDER = "SPIDER"
    CUSTOM = "CUSTOM"


class SearchArtifactStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class SearchRunStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkIdentifierType(enum.StrEnum):
    DOI = "DOI"
    OPENALEX_ID = "OPENALEX_ID"
    SEMANTIC_SCHOLAR_ID = "SEMANTIC_SCHOLAR_ID"
    PMID = "PMID"
    PMCID = "PMCID"
    ARXIV_ID = "ARXIV_ID"


class WorkVerificationType(enum.StrEnum):
    DOI_IDENTITY = "DOI_IDENTITY"
    METADATA_CONSISTENCY = "METADATA_CONSISTENCY"
    URL_ACCESS = "URL_ACCESS"
    SOURCE_EXISTENCE = "SOURCE_EXISTENCE"


class WorkVerificationStatus(enum.StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class DuplicateGroupType(enum.StrEnum):
    EXACT_DOI = "EXACT_DOI"
    EXTERNAL_ID = "EXTERNAL_ID"
    EXACT_TITLE = "EXACT_TITLE"
    FUZZY_TITLE = "FUZZY_TITLE"
    POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"


class DuplicateGroupStatus(enum.StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class DuplicateDecisionType(enum.StrEnum):
    MERGE = "MERGE"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class AgentDefinitionStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class AgentRunStatus(enum.StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"
    INVALID_INPUT = "INVALID_INPUT"
    FAILED = "FAILED"


class WorkflowRunStatus(enum.StrEnum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProjectEventActorType(enum.StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"

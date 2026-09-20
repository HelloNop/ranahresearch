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


class FullTextSourceType(enum.StrEnum):
    OPEN_ACCESS = "OPEN_ACCESS"
    USER_UPLOAD = "USER_UPLOAD"
    LICENSED_SOURCE = "LICENSED_SOURCE"
    OTHER = "OTHER"


class FullTextAssetStatus(enum.StrEnum):
    """State of one stored file, not of the retrieval attempt."""

    AVAILABLE = "AVAILABLE"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"
    REMOVED = "REMOVED"


class StudyType(enum.StrEnum):
    RCT = "RCT"
    QUASI_EXPERIMENTAL = "QUASI_EXPERIMENTAL"
    COHORT = "COHORT"
    CASE_CONTROL = "CASE_CONTROL"
    CROSS_SECTIONAL = "CROSS_SECTIONAL"
    QUALITATIVE = "QUALITATIVE"
    MIXED_METHODS = "MIXED_METHODS"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    OTHER = "OTHER"


class StudyStatus(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MERGED = "MERGED"


class StudyWorkRelationship(enum.StrEnum):
    PRIMARY_REPORT = "PRIMARY_REPORT"
    SECONDARY_REPORT = "SECONDARY_REPORT"
    CONFERENCE_ABSTRACT = "CONFERENCE_ABSTRACT"
    FOLLOW_UP = "FOLLOW_UP"
    PROTOCOL = "PROTOCOL"
    CORRECTION = "CORRECTION"
    OTHER = "OTHER"


class StudyLinkDecisionType(enum.StrEnum):
    LINK = "LINK"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    UNCERTAIN = "UNCERTAIN"


class FullTextAcquisitionStatus(enum.StrEnum):
    """Outcome of actually trying to obtain full text. ABSTRACT_ONLY and
    UNAVAILABLE are retrieval facts, never an agent's assumption."""

    NOT_REQUESTED = "NOT_REQUESTED"
    SEARCHING = "SEARCHING"
    AVAILABLE = "AVAILABLE"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    UNAVAILABLE = "UNAVAILABLE"
    RETRIEVAL_FAILED = "RETRIEVAL_FAILED"


class ExtractionSchemaStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class EvidenceValueType(enum.StrEnum):
    """How a value came to exist. DERIVED values must record their derivation,
    and MISSING is an explicit state, never a silent blank or a guess."""

    REPORTED = "REPORTED"
    DERIVED = "DERIVED"
    USER_ENTERED = "USER_ENTERED"
    MISSING = "MISSING"


class EvidenceVerificationStatus(enum.StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    CONFLICT = "CONFLICT"


class EvidenceStatus(enum.StrEnum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"

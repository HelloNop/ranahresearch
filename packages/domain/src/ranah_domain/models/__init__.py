"""All mapped models, imported here so Base.metadata sees every table."""

from ranah_domain.models.agent import AgentDefinition, AgentRun
from ranah_domain.models.dedupe import DuplicateDecision, DuplicateGroup, DuplicateMember
from ranah_domain.models.events import ProjectEvent, UsageEvent
from ranah_domain.models.manuscript import (
    Claim as Claim,
)
from ranah_domain.models.manuscript import (
    ClaimEvidenceLink as ClaimEvidenceLink,
)
from ranah_domain.models.manuscript import (
    ClaimStudyLink as ClaimStudyLink,
)
from ranah_domain.models.manuscript import (
    ClaimVerification as ClaimVerification,
)
from ranah_domain.models.manuscript import (
    EvidenceSynthesis as EvidenceSynthesis,
)
from ranah_domain.models.manuscript import (
    Manuscript as Manuscript,
)
from ranah_domain.models.manuscript import (
    ManuscriptCitation as ManuscriptCitation,
)
from ranah_domain.models.manuscript import (
    ManuscriptClaimLocation as ManuscriptClaimLocation,
)
from ranah_domain.models.manuscript import (
    ManuscriptExport as ManuscriptExport,
)
from ranah_domain.models.manuscript import (
    ManuscriptPlan as ManuscriptPlan,
)
from ranah_domain.models.manuscript import (
    ManuscriptSection as ManuscriptSection,
)
from ranah_domain.models.manuscript import (
    ManuscriptSectionPlan as ManuscriptSectionPlan,
)
from ranah_domain.models.manuscript import (
    ManuscriptVersion as ManuscriptVersion,
)
from ranah_domain.models.manuscript import (
    ResearchGap as ResearchGap,
)
from ranah_domain.models.manuscript import (
    ReviewIssue as ReviewIssue,
)
from ranah_domain.models.manuscript import (
    ReviewReport as ReviewReport,
)
from ranah_domain.models.manuscript import (
    RevisionTask as RevisionTask,
)
from ranah_domain.models.manuscript import (
    SectionPlanClaim as SectionPlanClaim,
)
from ranah_domain.models.manuscript import (
    SynthesisContradiction as SynthesisContradiction,
)
from ranah_domain.models.manuscript import (
    SynthesisEvidenceLink as SynthesisEvidenceLink,
)
from ranah_domain.models.manuscript import (
    SynthesisFinding as SynthesisFinding,
)
from ranah_domain.models.manuscript import (
    SynthesisTheme as SynthesisTheme,
)
from ranah_domain.models.manuscript import (
    TargetJournal as TargetJournal,
)
from ranah_domain.models.organization import Organization, ProjectMember, User
from ranah_domain.models.project import (
    ResearchFramework,
    ResearchIdea,
    ResearchPlan,
    ResearchProject,
    ResearchQuestion,
)
from ranah_domain.models.search import SearchQuery, SearchResult, SearchRun, SearchStrategy
from ranah_domain.models.work import (
    WorkIdentifier,
    WorkMetadataObservation,
    WorkRecord,
    WorkVerification,
)
from ranah_domain.models.workflow import WorkflowRun

__all__ = [
    "AgentDefinition",
    "AgentRun",
    "DuplicateDecision",
    "DuplicateGroup",
    "DuplicateMember",
    "Organization",
    "ProjectEvent",
    "ProjectMember",
    "ResearchFramework",
    "ResearchIdea",
    "ResearchPlan",
    "ResearchProject",
    "ResearchQuestion",
    "SearchQuery",
    "SearchResult",
    "SearchRun",
    "SearchStrategy",
    "UsageEvent",
    "User",
    "WorkIdentifier",
    "WorkMetadataObservation",
    "WorkRecord",
    "WorkVerification",
    "WorkflowRun",
]

from ranah_domain.models.evidence import (
    Evidence as Evidence,
)
from ranah_domain.models.evidence import (
    EvidenceProvenance as EvidenceProvenance,
)
from ranah_domain.models.evidence import (
    EvidenceVerification as EvidenceVerification,
)
from ranah_domain.models.evidence import (
    ExtractionSchema as ExtractionSchema,
)
from ranah_domain.models.evidence import (
    StudyCharacteristic as StudyCharacteristic,
)
from ranah_domain.models.fulltext import (
    DocumentChunk as DocumentChunk,
)
from ranah_domain.models.fulltext import (
    FullTextAcquisition as FullTextAcquisition,
)
from ranah_domain.models.fulltext import (
    FullTextAsset as FullTextAsset,
)
from ranah_domain.models.fulltext import (
    ParsedDocument as ParsedDocument,
)
from ranah_domain.models.risk_of_bias import RiskOfBiasAssessment as RiskOfBiasAssessment
from ranah_domain.models.risk_of_bias import RiskOfBiasDomain as RiskOfBiasDomain
from ranah_domain.models.screening import (
    EligibilityCriterion as EligibilityCriterion,
)
from ranah_domain.models.screening import (
    ProtocolAmendment as ProtocolAmendment,
)
from ranah_domain.models.screening import (
    ReviewProtocol as ReviewProtocol,
)
from ranah_domain.models.screening import (
    ScreeningDecision as ScreeningDecision,
)
from ranah_domain.models.study import (
    Study as Study,
)
from ranah_domain.models.study import (
    StudyLinkDecision as StudyLinkDecision,
)
from ranah_domain.models.study import (
    StudyWork as StudyWork,
)

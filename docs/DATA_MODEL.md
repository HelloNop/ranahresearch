# Data Model Specification v0.1

**Primary Persistence:** PostgreSQL  
**Product:** RanahResearch

---

# 1. Design Principles

ResearchProject is aggregate root.

Publication/WorkRecord != Study.

Evidence is first-class.

Claim != Evidence.

Manuscript is projection, not factual source of truth.

Critical scientific history is immutable/versioned.

---

# 2. Top-level Domain

Organization
→ User
→ ResearchProject
  → ResearchIdea
  → ResearchPlan
  → ResearchQuestion
  → ReviewProtocol
  → EligibilityCriteria
  → SearchStrategy
    → SearchQuery
      → SearchRun
        → SearchResult
  → WorkRecord
  → Study
    → StudyWork
    → ScreeningDecision
    → Evidence
    → Outcome
    → RiskOfBiasAssessment
  → Synthesis
  → Claim
  → MetaAnalysis
    → EffectSize
    → MetaAnalysisResult
  → Manuscript
    → ManuscriptVersion
  → ReviewReport
    → ReviewIssue
  → RevisionTask
  → ProjectEvent

---

# 3. Identity

Canonical IDs use UUID/UUIDv7/ULID-style identity.

Human aliases like S01 are display-only.

---

# 4. Organization

id
name
slug
plan
status
created_at
updated_at

Future:
billing_customer_id
settings
institutional_policy
data_region

---

# 5. User

id
organization_id
email
display_name
status
auth_provider
provider_subject
created_at
updated_at

---

# 6. ProjectMember

project_id
user_id
role
created_at

Roles:
OWNER
EDITOR
REVIEWER
VIEWER

---

# 7. ResearchProject

id
organization_id
created_by
title
working_title
description
research_method
status
language
target_journal_id
autonomy_mode
created_at
updated_at

Methods:
NARRATIVE_REVIEW
SCOPING_REVIEW
SYSTEMATIC_REVIEW
SYSTEMATIC_REVIEW_META_ANALYSIS

Future:
BIBLIOMETRIC
EMPIRICAL

---

# 8. Project Status

IDEA
EXPLORATION
PLANNING
PROTOCOL
SEARCHING
SCREENING
EXTRACTION
SYNTHESIS
ANALYSIS
WRITING
REVIEW
REVISION
AUTHOR_REVIEW
COMPLETED
ARCHIVED

---

# 9. ResearchIdea

id
project_id
raw_text
created_by
source
conversation_message_id
created_at

Original idea is preserved.

---

# 10. ResearchPlan

id
project_id
version
status
provisional_title
problem_statement
objective
scope_summary
recommended_method
recommended_framework
rationale
created_by_agent_run_id
approved_by
approved_at
created_at

Statuses:
DRAFT
PROPOSED
APPROVED
SUPERSEDED
REJECTED

---

# 11. ResearchQuestion

id
project_id
research_plan_id
question_type
question_text
is_primary
position
status
created_at

---

# 12. ResearchFramework

id
project_id
framework_type
version
structured_elements
rationale
created_at

Framework:
PICO
PICOS
PCC
SPIDER
CUSTOM

---

# 13. ReviewProtocol

id
project_id
version
status
background
objective
review_type
framework_id
screening_strategy
extraction_strategy
synthesis_strategy
meta_analysis_planned
created_at
approved_at
approved_by

---

# 14. ProtocolAmendment

id
protocol_id
from_version
to_version
field_path
old_value
new_value
reason
change_type
created_by
created_at

Change types:
PRE_SEARCH_CHANGE
POST_SEARCH_AMENDMENT
POST_SCREENING_AMENDMENT

---

# 15. EligibilityCriterion

id
protocol_id
dimension
operator
value
decision
reason
priority
created_at

Dimensions:
POPULATION
INTERVENTION
EXPOSURE
COMPARATOR
OUTCOME
STUDY_DESIGN
SETTING
PUBLICATION_TYPE
YEAR
LANGUAGE
COUNTRY
PEER_REVIEW
OTHER

---

# 16. SearchStrategy

id
project_id
protocol_id
version
status
description
created_at
approved_at

---

# 17. SearchConcept

id
search_strategy_id
label
position
created_at

---

# 18. SearchTerm

id
search_concept_id
term
term_type
source
created_at

Types:
KEYWORD
SYNONYM
CONTROLLED_VOCABULARY
ACRONYM
SPELLING_VARIANT

---

# 19. SearchQuery

id
search_strategy_id
provider
query_text
filters
version
status
created_at

---

# 20. SearchRun

id
project_id
search_query_id
provider
executed_query
executed_filters
started_at
completed_at
result_count_reported
result_count_retrieved
status
provider_metadata
agent_run_id

Statuses:
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
CANCELLED

---

# 21. SearchResult

id
search_run_id
provider_record_id
rank
raw_payload_location
normalized_payload
retrieved_at

---

# 22. WorkRecord

Canonical publication-level record.

id
project_id
doi
title
abstract
publication_year
publication_date
publication_type
journal
volume
issue
pages
publisher
language
url
open_access_status
created_at
updated_at

---

# 23. WorkIdentifier

work_id
provider
identifier_type
identifier
url

Types:
DOI
OPENALEX_ID
SEMANTIC_SCHOLAR_ID
PMID
PMCID
ARXIV_ID

---

# 24. Author / WorkAuthor

Author:
id
display_name
given_name
family_name
orcid

WorkAuthor:
work_id
author_id
position
is_corresponding

---

# 25. WorkMetadataObservation

id
work_id
provider
field_name
field_value
observed_at

Preserves metadata conflicts.

---

# 26. WorkVerification

id
work_id
verification_type
status
verified_by
details
verified_at

Types:
DOI_IDENTITY
METADATA_CONSISTENCY
URL_ACCESS
SOURCE_EXISTENCE

Statuses:
VERIFIED
PARTIALLY_VERIFIED
UNVERIFIED
CONFLICT
FAILED

---

# 27. DuplicateGroup

id
project_id
duplicate_type
status
created_at
resolved_at

Types:
EXACT_DOI
EXTERNAL_ID
EXACT_TITLE
FUZZY_TITLE
POTENTIAL_DUPLICATE

---

# 28. DuplicateMember

duplicate_group_id
work_id
similarity_score
signals

---

# 29. DuplicateDecision

id
duplicate_group_id
canonical_work_id
decision
reason
resolved_by
created_at

MERGE
KEEP_SEPARATE
REVIEW_REQUIRED

---

# 30. Study

Underlying research study.

id
project_id
study_label
title
study_type
status
country
setting
recruitment_period
created_at
updated_at

Types:
RCT
QUASI_EXPERIMENTAL
COHORT
CASE_CONTROL
CROSS_SECTIONAL
QUALITATIVE
MIXED_METHODS
SYSTEMATIC_REVIEW
OTHER

---

# 31. StudyWork

study_id
work_id
relationship_type
confidence
linked_by
created_at

Relationship:
PRIMARY_REPORT
SECONDARY_REPORT
CONFERENCE_ABSTRACT
FOLLOW_UP
PROTOCOL
CORRECTION
OTHER

---

# 32. ScreeningStage

TITLE_ABSTRACT
FULL_TEXT

---

# 33. ScreeningDecision

Immutable.

id
project_id
work_id
study_id
stage
decision
reason_code
rationale
confidence
reviewer_type
reviewer_id
agent_run_id
criteria_version
created_at

Decision:
INCLUDE
EXCLUDE
UNCERTAIN
CONFLICT

Reviewer:
AI
HUMAN
SYSTEM

---

# 34. ExclusionReason

code
label
description
applicable_stage

Examples:
WRONG_POPULATION
WRONG_INTERVENTION
WRONG_OUTCOME
WRONG_STUDY_DESIGN
NOT_PRIMARY_RESEARCH
DUPLICATE_STUDY
OUTSIDE_DATE_RANGE
FULL_TEXT_UNAVAILABLE

---

# 35. FullTextAsset

id
work_id
storage_key
source_type
mime_type
sha256
status
retrieved_at
uploaded_by
license_metadata

Source:
OPEN_ACCESS
USER_UPLOAD
LICENSED_SOURCE
OTHER

Status:
AVAILABLE
PARSING
PARSED
FAILED
REMOVED

---

# 36. ParsedDocument

id
full_text_asset_id
parser_version
page_count
structure
created_at

---

# 37. DocumentChunk

id
parsed_document_id
page_start
page_end
section_path
text
token_count
embedding
created_at

---

# 38. ExtractionSchema

id
project_id
protocol_id
version
schema_json
status
created_at
approved_at

---

# 39. Evidence

id
project_id
study_id
work_id
evidence_type
field_name
value_json
unit
confidence
verification_status
extractor_run_id
created_at
updated_at

---

# 40. EvidenceProvenance

id
evidence_id
parsed_document_id
chunk_id
page
section
quote_start
quote_end
evidence_text
created_at

---

# 41. EvidenceVerification

id
evidence_id
verification_method
status
confidence
reviewer_id
agent_run_id
notes
created_at

Statuses:
VERIFIED
PARTIAL
CONFLICT
UNVERIFIED

---

# 42. StudyCharacteristic

id
study_id
dimension
value_json
evidence_id

Dimensions:
POPULATION
COUNTRY
SETTING
SAMPLE_SIZE
DESIGN
INTERVENTION
COMPARATOR
DURATION

---

# 43. Outcome

id
study_id
name
normalized_name
outcome_type
timepoint
measurement_tool
direction
unit
created_at

Types:
CONTINUOUS
BINARY
CORRELATION
TIME_TO_EVENT
OTHER

---

# 44. OutcomeArm

id
outcome_id
arm_name
role
sample_size
mean
sd
events
total
other_statistics

Role:
INTERVENTION
COMPARATOR
OTHER

---

# 45. RiskOfBiasAssessment

id
project_id
study_id
tool
tool_version
overall_judgement
status
reviewer_id
created_at

---

# 46. RiskOfBiasDomain

id
assessment_id
domain_code
judgement
rationale
supporting_evidence

---

# 47. Synthesis

id
project_id
version
synthesis_type
scope
status
summary
created_by_agent_run_id
created_at

Types:
NARRATIVE
THEMATIC
SCOPING
SYSTEMATIC

---

# 48. Theme

id
synthesis_id
label
description
position

---

# 49. ThemeEvidence

theme_id
evidence_id
relationship
weight

SUPPORTS
CONTRADICTS
CONTEXTUAL

---

# 50. ResearchGap

id
project_id
synthesis_id
gap_type
description
supporting_evidence
confidence
created_at

Types:
POPULATION
METHOD
OUTCOME
GEOGRAPHICAL
TEMPORAL
THEORETICAL
EVIDENCE_CONSISTENCY
OTHER

---

# 51. Claim

id
project_id
claim_text
claim_type
scope
strength
status
created_by_agent_run_id
created_at
updated_at

Types:
DESCRIPTIVE
COMPARATIVE
ASSOCIATIONAL
CAUSAL
METHODOLOGICAL
INTERPRETIVE

---

# 52. ClaimEvidenceLink

claim_id
evidence_id
relationship
confidence
created_at

SUPPORTS
PARTIALLY_SUPPORTS
CONTRADICTS
UNCERTAIN

---

# 53. ClaimVerification

id
claim_id
status
confidence
reasoning
reviewer_run_id
created_at

SUPPORTED
PARTIALLY_SUPPORTED
CONTRADICTED
UNCERTAIN
UNSUPPORTED

---

# 54. MetaAnalysis

id
project_id
name
outcome_definition
effect_measure
model
status
protocol_version
created_at

Models:
COMMON_EFFECT
RANDOM_EFFECTS

---

# 55. MetaAnalysisStudy

meta_analysis_id
study_id
outcome_id
inclusion_status
exclusion_reason

---

# 56. EffectSize

id
meta_analysis_id
study_id
outcome_id
effect_measure
estimate
standard_error
variance
ci_lower
ci_upper
calculation_method
created_at

---

# 57. EffectSizeInput

id
effect_size_id
input_name
value
unit
evidence_id

---

# 58. MetaAnalysisResult

id
meta_analysis_id
pooled_estimate
standard_error
ci_lower
ci_upper
q
q_p_value
i_squared
tau_squared
prediction_interval_lower
prediction_interval_upper
study_count
analysis_config
engine_version
created_at

---

# 59. SensitivityAnalysis

id
meta_analysis_id
name
configuration
result
created_at

---

# 60. SubgroupAnalysis

id
meta_analysis_id
moderator
groups
result
is_prespecified
created_at

---

# 61. AnalysisArtifact

id
analysis_id
artifact_type
storage_key
created_at

Types:
FOREST_PLOT
FUNNEL_PLOT
TABLE
CSV
JSON

---

# 62. Manuscript

id
project_id
current_version_id
status
target_journal_id
created_at
updated_at

DRAFTING
INTERNAL_REVIEW
REVISION
AUTHOR_REVIEW
SUBMISSION_CANDIDATE

---

# 63. ManuscriptVersion

id
manuscript_id
version_number
title
abstract
created_by
created_by_agent_run_id
created_at

Immutable.

---

# 64. ManuscriptSection

id
manuscript_version_id
section_type
title
position
content
word_count

---

# 65. ManuscriptClaimLocation

section_id
claim_id
start_offset
end_offset

---

# 66. ManuscriptCitation

section_id
work_id
citation_key
start_offset
end_offset

---

# 67. ReviewReport

id
project_id
manuscript_version_id
reviewer_type
reviewer_version
status
overall_summary
created_at

Types:
SCIENTIFIC
EVIDENCE
CITATION
COVERAGE
SEARCH
SCREENING
RISK_OF_BIAS
STATISTICAL
WRITING
JOURNAL

---

# 68. ReviewIssue

id
review_report_id
project_id
severity
category
description
section_id
claim_id
status
suggested_action
created_at
resolved_at

Severity:
CRITICAL
MAJOR
MINOR
ADVISORY

Status:
OPEN
IN_PROGRESS
RESOLVED
DISMISSED
REOPENED

---

# 69. RevisionTask

id
project_id
review_issue_id
task_type
assigned_agent
status
instructions
created_at
completed_at

RESEARCH
REWRITE
REANALYZE
VERIFY_CITATION
VERIFY_EVIDENCE
RECALCULATE
USER_DECISION

---

# 70. AgentDefinition

id
name
version
description
input_schema
output_schema
prompt_version
status
created_at

---

# 71. AgentRun

id
project_id
agent_definition_id
workflow_id
task_type
status
model_provider
model_name
prompt_version
started_at
completed_at
input_tokens
output_tokens
estimated_cost
error_code

---

# 72. AgentRunInput

agent_run_id
artifact_type
artifact_id
artifact_version

---

# 73. AgentRunOutput

agent_run_id
artifact_type
artifact_id
artifact_version

---

# 74. WorkflowRun

id
project_id
temporal_workflow_id
workflow_type
status
started_at
completed_at

---

# 75. Operation

id
project_id
workflow_run_id
operation_type
status
progress
created_at
completed_at

---

# 76. ProjectEvent

Append-only.

id
project_id
event_type
actor_type
actor_id
payload
created_at

Actors:
USER
AGENT
SYSTEM

---

# 77. HumanOverride

id
project_id
entity_type
entity_id
previous_value
new_value
reason
user_id
created_at

---

# 78. UsageEvent

id
organization_id
user_id
project_id
event_type
quantity
unit
cost_estimate
provider
created_at

---

# 79. Export

id
project_id
manuscript_version_id
export_type
status
storage_key
created_at

DOCX
PDF
LATEX
MARKDOWN
BIBTEX
RIS
CSV
REPRODUCIBILITY_BUNDLE

---

# 80. TargetJournal

id
name
publisher
url
scope
active

---

# 81. JournalRequirement

id
journal_id
article_type
requirement_type
value
source
verified_at

---

# 82. Conversation

id
project_id
created_at

---

# 83. Message

id
conversation_id
role
content
created_at

USER
ASSISTANT
SYSTEM_EVENT

---

# 84. Chat Does Not Mutate Science Directly

Natural-language commands become structured operations/artifacts.

Example:
“Exclude papers before 2020.”
→ Protocol Amendment.

---

# 85. Embeddings

Potential:
DocumentChunk
Evidence
Claim
StudyAbstract
Theme

Do not embed every row.

---

# 86. Soft Delete

Scientific entities generally use status/deleted_at/superseded_by instead of destructive delete.

---

# 87. Unique Constraints

Examples:
WorkIdentifier(provider, identifier)
SearchResult(search_run_id, provider_record_id)
ProjectMember(project_id, user_id)
StudyWork(study_id, work_id)
ClaimEvidenceLink(claim_id, evidence_id)

---

# 88. Important Indexes

project_id
organization_id
doi
publication_year
screening status
work identifiers
evidence study_id
outcome normalized_name
claim project_id
review issue status
workflow status
created_at

Vector indexes when necessary.

---

# 89. JSONB

Use for flexible secondary data:
provider metadata, framework elements, analysis config, schema snapshots.

Do not put entire domain in JSONB.

---

# 90. Object Storage

Large binary artifacts use storage keys, not DB blobs.

---

# 91. Data Ownership

Every scientific entity must be safely scoped to organization/project.

---

# 92. Canonical SLR Flow

ResearchProject
→ ReviewProtocol
→ SearchStrategy
→ SearchQuery
→ SearchRun
→ SearchResult
→ WorkRecord
→ DuplicateGroup
→ Study
→ ScreeningDecision
→ Evidence
→ RiskOfBias
→ Synthesis
→ Claim
→ Manuscript

---

# 93. Canonical Meta-analysis Flow

Study
→ Outcome
→ OutcomeArm
→ Evidence
→ EffectSizeInput
→ EffectSize
→ MetaAnalysis
→ MetaAnalysisResult
→ AnalysisArtifact

---

# 94. Canonical Claim Flow

Evidence
→ ClaimEvidenceLink
→ Claim
→ ClaimVerification
→ ManuscriptClaimLocation

---

# 95. Canonical Reviewer Flow

ManuscriptVersion
→ ReviewReport
→ ReviewIssue
→ RevisionTask
→ AgentRun
→ New ManuscriptVersion
→ Re-review

---

# 96. OpenDraft Structures Not Used

No:
- DraftContext
- citation_database.json as canonical DB
- checkpoint.json
- phase-output string state

---

# 97. OpenDraft Mapping

Provider citation-like metadata → ProviderWork → WorkRecord + MetadataObservation.

OpenDraft Citation is never canonical domain object.

---

# 98. MVP Data Model Phase 1

Organization
User
ResearchProject
ResearchIdea
ResearchPlan
ResearchQuestion
ResearchFramework
SearchStrategy
SearchQuery
SearchRun
SearchResult
WorkRecord
WorkIdentifier
WorkMetadataObservation
WorkVerification
DuplicateGroup
DuplicateDecision
AgentDefinition
AgentRun
WorkflowRun
ProjectEvent
UsageEvent

---

# 99. MVP Phase 2

ReviewProtocol
EligibilityCriterion
Study
StudyWork
ScreeningDecision
FullTextAsset
ParsedDocument
DocumentChunk
ExtractionSchema
Evidence
EvidenceProvenance

---

# 100. MVP Phase 3

Synthesis
Theme
ResearchGap
Claim
ClaimEvidenceLink
ClaimVerification
Manuscript
ManuscriptVersion
ManuscriptSection
ReviewReport
ReviewIssue
RevisionTask

---

# 101. MVP Phase 4

Outcome
OutcomeArm
RiskOfBiasAssessment
RiskOfBiasDomain
MetaAnalysis
MetaAnalysisStudy
EffectSizeInput
EffectSize
MetaAnalysisResult
SensitivityAnalysis
SubgroupAnalysis
AnalysisArtifact

---

# 102. Data Model Testing

Test:
- FK integrity;
- tenant isolation;
- artifact versioning;
- immutable screening history;
- protocol amendment history;
- dedupe integrity;
- study-work linking;
- claim-evidence integrity;
- analysis traceability;
- review revision history.

---

# 103. Invariant: Included Study

For methods requiring full-text screening, final included state derives from latest valid full-text INCLUDE decision.

---

# 104. Invariant: Meta-analysis Input

No EffectSizeInput without Evidence provenance unless explicitly USER_ENTERED with attribution.

---

# 105. Invariant: Manuscript Citation

Final citations must point to WorkRecord.

---

# 106. Invariant: Claim Support

Major scientific claims cannot be verified with zero supporting evidence unless explicitly labeled author interpretation.

---

# 107. Invariant: PRISMA Counts

Derived from search/dedupe/screen/study state.

---

# 108. Invariant: Historical Decisions

Overrides create new immutable decisions.

---

# 109. Data Model North Star

The DB must answer:
Why was this included/excluded?
Where did this number come from?
Which evidence supports this sentence?
Which study contradicts it?
How was this effect calculated?
Which protocol version was used?
Which agent/model made this decision?
Did a human override it?
Which revision resolved an issue?

---

# 110. Final Hierarchies

Knowledge:
SOURCE → WORK → STUDY → EVIDENCE → SYNTHESIS → CLAIM → MANUSCRIPT

Workflow:
PLAN → PROTOCOL → SEARCH → SCREEN → EXTRACT → SYNTHESIZE → ANALYZE → WRITE → REVIEW → REVISE

Audit:
WORKFLOW RUN → AGENT RUN → INPUT ARTIFACT VERSION → OUTPUT ARTIFACT VERSION → PROJECT EVENT

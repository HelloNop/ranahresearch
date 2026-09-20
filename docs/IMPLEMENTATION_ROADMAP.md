# Implementation Roadmap & Epic Breakdown v0.1

**Product:** RanahResearch  
**Status:** Execution Planning

---

# 1. Execution Strategy

Build vertical slices, not all infrastructure first.

Foundation
→ Vertical Slice 1: Idea → Plan → Literature
→ Vertical Slice 2: Protocol → Screening → Evidence
→ Vertical Slice 3: Synthesis → Claims → Manuscript → Review
→ Vertical Slice 4: Meta-analysis
→ Production Hardening

---

# 2. Milestones

M0 — Repository & Engineering Foundation

M1 — Research Discovery MVP

M2 — Systematic Review Core

M3 — Evidence-to-Manuscript

M4 — Meta-analysis

M5 — SaaS Production Readiness

---

# 3. Epic Overview

EPIC-001 Repository Foundation  
EPIC-002 Local Development Infrastructure  
EPIC-003 Core Domain & Database  
EPIC-004 Authentication & Tenancy  
EPIC-005 Durable Workflow Runtime  
EPIC-006 LLM Gateway  
EPIC-007 Agent Runtime  
EPIC-008 Academic Provider Foundation  
EPIC-009 OpenDraft Provider Adoption  
EPIC-010 Literature Normalization  
EPIC-011 Literature Deduplication  
EPIC-012 Source Verification  
EPIC-013 Research Project API  
EPIC-014 Research Director  
EPIC-015 Research Framework Selector  
EPIC-016 Search Strategist  
EPIC-017 Literature Search Orchestration  
EPIC-018 Research Workspace UI  

EPIC-019 Protocol Engine  
EPIC-020 Eligibility Criteria  
EPIC-021 Screening Engine  
EPIC-022 Screening UI  
EPIC-023 Full-text Acquisition  
EPIC-024 PDF / Document Parsing  
EPIC-025 Evidence Extraction  
EPIC-026 Evidence Validation  
EPIC-027 Evidence Matrix UI  
EPIC-028 Study Linking  
EPIC-029 Risk-of-Bias Foundation  

EPIC-030 Evidence Synthesis  
EPIC-031 Claim Graph  
EPIC-032 Manuscript Model  
EPIC-033 Manuscript Planner  
EPIC-034 Manuscript Writer  
EPIC-035 Citation Resolver  
EPIC-036 Reviewer Council  
EPIC-037 Revision Loop  
EPIC-038 Manuscript Workspace UI  
EPIC-039 Export Service  

EPIC-040 Outcome Data Model  
EPIC-041 Meta-analysis Eligibility  
EPIC-042 Effect Size Engine  
EPIC-043 Pooling Engine  
EPIC-044 Heterogeneity  
EPIC-045 Forest Plot  
EPIC-046 Sensitivity Analysis  
EPIC-047 Statistical Reviewer  
EPIC-048 Meta-analysis UI  

EPIC-049 Usage Metering  
EPIC-050 Billing & Plans  
EPIC-051 Observability  
EPIC-052 Security Hardening  
EPIC-053 Scientific Evaluation Suite  
EPIC-054 Performance & Scaling  
EPIC-055 Production Deployment

---

# 4. EPIC-001 — Repository Foundation

Objective:
create new repository foundation.

Structure:
apps/web
apps/api
packages/domain
packages/agents
packages/llm
packages/literature
packages/evidence
packages/review
packages/statistics
packages/documents
workers
prompts
tests
evals
docs
infra

Tasks:
- init Git;
- Python workspace;
- Node workspace;
- editorconfig;
- gitignore;
- README;
- foundation docs;
- third-party notice structure;
- branch strategy.

Acceptance:
repo builds;
Python imports;
web starts;
API starts;
CI basic checks.

---

# 5. EPIC-002 — Local Infrastructure

Postgres
Temporal
Temporal UI
Redis optional
local S3-compatible storage

One-command local start.

---

# 6. EPIC-003 — Core Domain & Database

Initial tables:
organizations
users
project_members
research_projects
research_ideas
research_plans
research_questions
research_frameworks
search_strategies
search_queries
search_runs
search_results
work_records
work_identifiers
work_metadata_observations
work_verifications
duplicate_groups
duplicate_members
duplicate_decisions
agent_definitions
agent_runs
workflow_runs
project_events
usage_events

Use SQLAlchemy, Pydantic, Alembic.

---

# 7. EPIC-004 — Authentication & Tenancy

Auth provider integration
organization/user bootstrap
project membership
authorization
tenant-scoped repository.

---

# 8. EPIC-005 — Temporal

Temporal client
workers
workflow/activity base
retry
workflow IDs
operation status
cancellation
signals.

Test worker crash/resume.

---

# 9. EPIC-006 — LLM Gateway

generate
generate_structured
tool_call
embed

OpenAI initially.

Centralize usage, retry, cost, tracing, routing.

---

# 10. EPIC-007 — Agent Runtime

AgentRegistry
AgentContract
AgentContext
AgentTask
AgentResult
ContextBuilder
ToolRegistry

Implement permissions, prompt versioning, AgentRun persistence, validation.

---

# 11. EPIC-008 — Academic Provider Foundation

Define:
AcademicProvider
ProviderWork
SearchRequest
SearchPage
ProviderCapability

Fake/test provider must pass shared contract suite.

---

# 12. EPIC-009 — OpenDraft Provider Adoption

Adapt:
CrossrefProvider
OpenAlexProvider
SemanticScholarProvider

From OpenDraft provider code.

Rewrite:
async
pagination
provider interfaces
tracing
quotas
SaaS concerns.

---

# 13. EPIC-010 — Literature Normalization

ProviderWork
→ identifier/DOI/title/author normalization
→ metadata observations
→ WorkRecord.

---

# 14. EPIC-011 — Deduplication

1. DOI
2. IDs
3. exact normalized title
4. blocked fuzzy candidates
5. uncertain resolution

No destructive deletion.

---

# 15. EPIC-012 — Source Verification

Identity confidence separated from eligibility.

Unverified != excluded.

---

# 16. EPIC-013 — Project API

POST /projects
GET /projects
GET /projects/{id}
POST /projects/{id}/messages
GET /projects/{id}/events

---

# 17. EPIC-014 — Research Director

Idea → structured ResearchPlan.

---

# 18. EPIC-015 — Framework Selector

PICO/PICOS/PCC/SPIDER/CUSTOM.

---

# 19. EPIC-016 — Search Strategist

Plan/framework → concepts + provider queries + filters + rationale.

---

# 20. EPIC-017 — Literature Search Orchestration

ResearchPlan
→ SearchStrategy
→ parallel providers
→ SearchRuns
→ normalization
→ dedupe
→ verification.

Temporal workflow.

---

# 21. EPIC-018 — Research Workspace UI

Implementation status (2026-09-20): COMPLETE for blocking discovery UI gaps.
EPIC-019, EPIC-020, EPIC-021 and EPIC-022 are COMPLETE for the title/abstract
screening scope. FULL_TEXT execution remains deferred to the acquisition/parsing
foundation. See [implementation report](EPIC_018_022_IMPLEMENTATION.md) for
acceptance evidence, commands, resolver semantics and remaining boundaries.

Project chat
Research Plan
Literature list
Activity/search progress.

Completes M1.

---

# 22. M1 Definition of Done

Sign in
→ create project
→ idea
→ plan
→ approve
→ search
→ normalized literature.

---

# 23. EPIC-019 — Protocol Engine

Versioned approved ReviewProtocol.

Systematic Review final search requires protocol.

---

# 24. EPIC-020 — Eligibility Criteria

Machine-readable criterion editor/evaluator/versioning.

---

# 25. EPIC-021 — Screening Engine

Title/abstract + full text.

Structured decision/reason/confidence/provenance/immutable history/user override.

---

# 26. EPIC-022 — Screening UI

Dedicated rapid screening workspace with criteria and AI recommendations.

---

# 27. EPIC-023 — Full-text Acquisition

OA/user/licensed/abstract-only/unavailable.

No bypass.

---

# 28. EPIC-024 — Document Parsing

Asset → parser → pages → sections → chunks → embeddings.

Preserve provenance.

---

# 29. EPIC-025 — Evidence Extraction

Structured protocol-driven extraction.

---

# 30. EPIC-026 — Evidence Validation

Schema/numerical rules + second-pass reviewer.

---

# 31. EPIC-027 — Evidence Matrix UI

Study/design/population/N/intervention/comparator/outcome/finding/RoB.

User corrections audited.

---

# 32. EPIC-028 — Study Linking

Multiple publications → one Study.

Conservative AI resolution.

---

# 33. EPIC-029 — Risk-of-Bias Foundation

Assessment registry + domain judgments + evidence.

---

# 34. M2 Definition of Done

Protocol
→ reproducible search
→ dedupe
→ screen
→ full-text
→ extraction
→ evidence matrix.

---

# 35. EPIC-030 — Evidence Synthesis

Themes
patterns
contradictions
uncertainty
gaps
candidate claims.

---

# 36. EPIC-031 — Claim Graph

First-class claims with support/contradiction/confidence.

---

# 37. EPIC-032 — Manuscript Model

Versioned manuscript/sections/claim/citation mappings.

---

# 38. EPIC-033 — Manuscript Planner

Outline
section objectives
claim allocation
table/figure plan.

---

# 39. EPIC-034 — Manuscript Writer

Section-by-section, evidence-grounded.

---

# 40. EPIC-035 — Citation Resolver

Deterministic WorkRecord-based formatting.

Prefer CSL.

No compile-time literature search.

---

# 41. EPIC-036 — Reviewer Council

Initial:
Scientific
Claim/Evidence
Citation
Writing
Methodology.

---

# 42. EPIC-037 — Revision Loop

Issue
→ RevisionPlanner
→ research/analysis/rewrite
→ new version
→ reviewer recheck.

---

# 43. EPIC-038 — Manuscript UI

Sections
citations
evidence inspector
review issues
versions
diff.

---

# 44. EPIC-039 — Export

Markdown
DOCX
PDF
LaTeX
BibTeX.

---

# 45. M3 Definition of Done

Evidence
→ synthesis
→ claims
→ manuscript
→ review
→ revision
→ export.

---

# 46. EPIC-040 — Outcome Model

Outcome
OutcomeArm
numeric evidence links.

---

# 47. EPIC-041 — Meta-analysis Eligibility

APPROPRIATE
APPROPRIATE_WITH_SUBGROUPS
POSSIBLE_BUT_HIGH_RISK
NOT_APPROPRIATE
INSUFFICIENT_DATA.

---

# 48. EPIC-042 — Effect Size Engine

MD
SMD
RR
OR
RD
Fisher z.

Golden tests required.

---

# 49. EPIC-043 — Pooling Engine

Common/fixed
random
weights
pooled estimate
CI.

---

# 50. EPIC-044 — Heterogeneity

Q
I²
τ²
prediction interval where appropriate.

---

# 51. EPIC-045 — Forest Plot

Deterministic result visualization.

---

# 52. EPIC-046 — Sensitivity

Exclude high RoB
influential studies
alternate models
imputed values.

---

# 53. EPIC-047 — Statistical Reviewer

Detect wrong direction/measure/mapping/pooling/interpretation.

---

# 54. EPIC-048 — Meta-analysis UI

Raw inputs
study inclusion
effect sizes
model
heterogeneity
forest plot
sensitivity.

---

# 55. M4 Definition of Done

Quantitative evidence
→ effect sizes
→ pooling
→ heterogeneity
→ forest plot
→ review
→ manuscript integration.

---

# 56. EPIC-049 — Usage Metering

LLM
search
embedding
PDF
screening
extraction
storage
analysis
exports.

---

# 57. EPIC-050 — Billing

Stripe
plans
entitlements
quotas.

---

# 58. EPIC-051 — Observability

OpenTelemetry
logs
errors
workflow metrics
cost metrics
scientific metrics.

---

# 59. EPIC-052 — Security Hardening

Tenant tests
secret manager
signed objects
upload scanning
rate limits
permissions
dependency scans
retention/deletion.

---

# 60. EPIC-053 — Scientific Evaluation Suite

Benchmarks:
search
dedupe
screening
study linking
extraction
claim entailment
citation
statistics
reviewers.

---

# 61. EPIC-054 — Performance

Test:
5k/10k records
large PDFs
parallel screening
large evidence corpora.

Optimize batching/indexes/concurrency.

---

# 62. EPIC-055 — Production Deployment

web
API
workers
managed Postgres
S3
Temporal
secrets
monitoring
backup/PITR
TLS
CI/CD.

---

# 63. M5 Definition of Done

auth
tenant isolation
billing
quotas
monitoring
backup
security
deployment automation
scientific eval gates.

---

# 64. Recommended Build Order

EPIC-001
→ 002
→ 003
→ 005
→ 006
→ 007
→ 008
→ 009
→ 010
→ 011
→ 012
→ 013
→ 014
→ 015
→ 016
→ 017
→ 018.

Authentication can be integrated in parallel early.

---

# 65. Parallel Workstreams

Platform — DB/Temporal/Auth/Observability/Billing.

Literature — providers/normalization/dedup/verification/search.

Agent Intelligence — Research Director/Protocol/Screening/Extraction/Synthesis/Writer/Reviewers.

Scientific Computation — outcomes/effects/meta-analysis/plots/golden tests.

UX — chat/literature/screening/evidence/manuscript/analysis.

---

# 66. First Coding Target

AcademicProvider interface
→ CrossrefProvider
→ OpenAlexProvider
→ SemanticScholarProvider
→ ProviderWork
→ WorkRecord.

Literature engine is the first core dependency.

---

# 67. First End-to-End Demo

User enters research idea.

System:
1. create project
2. Research Director generates plan
3. user approves
4. Search Strategist generates queries
5. OpenAlex search
6. Crossref search
7. Semantic Scholar search
8. normalize
9. dedupe
10. verify source identity
11. display literature

---

# 68. Engineering Quality Gates

Every epic needs:
code
tests
telemetry
error handling
docs
acceptance test.

Scientific components additionally need:
benchmark/eval
provenance
failure-to-unknown behavior.

---

# 69. Pull Request Rules

Bounded capability
tests
no unrelated refactors
epic/task reference
migration/docs updates
MIT attribution where needed.

---

# 70. OpenDraft Adoption Tasks

OD-001 Crossref mapping  
OD-002 OpenAlex abstract reconstruction  
OD-003 Semantic Scholar IDs  
OD-004 provider retry/rate limits  
OD-005 DOI/source verification  
OD-006 dedupe concepts  
OD-007 MIT notices  
OD-008 export/Pandoc evaluation

---

# 71. Architecture Guardrails

Do not introduce:
- DraftContext/global project object;
- provider calls scattered through business logic;
- filesystem as DB;
- giant article generation endpoint;
- LLM statistical calculations;
- model-memory citations;
- metadata heuristics as hard SLR exclusion.

---

# 72. Scope Guardrails

Do not prematurely build:
microservices
Kubernetes
dedicated vector DB
network meta-analysis
bibliometrics
empirical experiments
auto journal submission
complex organization features.

---

# 73. Definition of Alpha

M1 + M2 + basic M3.

---

# 74. Definition of Private Beta

Full M3 + initial M4 + basic production infra + scientific eval suite.

---

# 75. Definition of v1

Credible support for:
Narrative
Scoping
Systematic Review
basic pairwise Meta-analysis

with traceability/audit/review/export/billing/reliability.

---

# 76. Immediate Next Action

Implement EPIC-001 Repository Foundation, then 002/003/005/006/008/009.

The first core implementation target is the Literature Engine.

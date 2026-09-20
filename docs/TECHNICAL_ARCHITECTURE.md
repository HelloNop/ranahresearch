# Technical Architecture Specification v0.1

**Product:** RanahResearch  
**Architecture Style:** Modular Monolith + Durable Workflow Workers  
**Primary Language:** Python + TypeScript  
**Primary Database:** PostgreSQL  
**Workflow Engine:** Temporal  
**Vector Retrieval:** pgvector  
**Object Storage:** S3-compatible  
**Initial LLM Provider:** OpenAI behind provider abstraction  
**Academic Providers:** OpenAlex, Crossref, Semantic Scholar

---

# 1. Purpose

Defines SaaS architecture, agent runtime, workflows, persistence, retrieval,
academic providers, statistical computation, storage, multi-tenancy,
observability, security, and deployment.

---

# 2. Architectural Principles

1. Database is source of truth.
2. Agents are stateless workers.
3. Workflow state is durable.
4. LLM is not the database.
5. LLM is not the calculator.
6. Scientific operations are auditable.
7. Provider independence.
8. Start as modular monolith.

---

# 3. High-level Architecture

WEB CLIENT (Next.js/TypeScript)
→ FastAPI API
→ PostgreSQL + pgvector
→ S3-compatible object storage
→ Temporal
→ worker pools
→ scientific core / agents / academic providers / deterministic computation.

---

# 4. Recommended Technology Stack

Frontend — Next.js + React + TypeScript  
UI — Tailwind + component system  
Backend — Python + FastAPI  
Validation — Pydantic  
ORM — SQLAlchemy  
Migrations — Alembic  
Workflow — Temporal  
Database — PostgreSQL  
Vector — pgvector  
Object Storage — S3-compatible  
Cache — Redis optional  
LLM — internal provider abstraction, OpenAI initially  
Academic — OpenAlex, Crossref, Semantic Scholar  
Stats — NumPy, pandas, SciPy, statsmodels + tested internal meta-analysis code  
Documents — Pandoc  
Citations — CSL-compatible formatter  
Auth — managed OAuth/OIDC  
Billing — Stripe  
Observability — OpenTelemetry + error tracking  
Container — Docker  
CI/CD — GitHub Actions

---

# 5. Repository Strategy

New repository; OpenDraft is not a production dependency.

Suggested monorepo:

/
├── apps/
│   ├── web/
│   └── api/
├── workers/
│   ├── orchestration/
│   ├── research/
│   ├── document/
│   └── statistics/
├── packages/
│   ├── domain/
│   ├── agents/
│   ├── llm/
│   ├── literature/
│   ├── evidence/
│   ├── review/
│   ├── statistics/
│   └── documents/
├── prompts/
├── evals/
├── tests/
├── docs/
└── infra/

---

# 6. Frontend Architecture

Frontend is not only chat.

Workspaces:
- Dashboard
- Chat
- Research Plan
- Protocol
- Literature
- Screening
- Evidence
- Analysis
- Manuscript
- Review
- Export

---

# 7. Main Frontend Screens

Dashboard — project status/progress.

Research Workspace — conversational collaboration.

Protocol Workspace — structured protocol editor.

Literature Workspace — discovered/canonical records.

Screening Workspace — title/abstract/full-text decisions.

Evidence Workspace — evidence matrix.

Meta-analysis Workspace — outcomes/effects/forest plots.

Manuscript Workspace — versioned writing/evidence/review.

Review Workspace — reviewer issues/revisions.

---

# 8. Backend API

FastAPI handles:
- auth;
- authorization;
- project CRUD;
- queries;
- workflow commands;
- user actions;
- billing;
- exports;
- streaming progress.

Long-running tasks never run in normal HTTP lifecycle.

---

# 9. API Command Pattern

Frontend sends command.

API:
1. validate;
2. authorize;
3. create operation/workflow;
4. return operation_id.

Workers continue asynchronously.

---

# 10. Durable Workflow Engine

Use Temporal for:
- long-running operations;
- retries;
- worker failure recovery;
- human approval waits;
- resumability;
- execution history.

---

# 11. Temporal Architecture

Example ScientificProjectWorkflow:
- brainstorm activity
- exploratory search
- wait plan approval
- build protocol
- wait protocol approval
- search
- dedupe
- screening
- extraction
- synthesis
- analysis
- writing
- review
- revision

External API/LLM calls are Temporal Activities, not deterministic workflow code.

---

# 12. Workflow Granularity

Avoid:
generate_entire_paper()

Prefer:
- generate_search_queries
- search_openalex
- search_crossref
- normalize_records
- deduplicate_records
- screen_batch
- extract_batch
- synthesize_theme
- write_section
- review_section

---

# 13. Scientific Orchestrator

Reads:
- project state;
- methodology requirements;
- artifacts;
- tasks;
- review issues;
- user instructions.

Returns:
- next action;
- agent;
- tool;
- dependencies;
- reason;
- human approval requirement.

---

# 14. Orchestrator Decision Model

Example:
SEARCH_COMPLETE → screening required.

Dynamic example:
SYNTHESIS → evidence insufficient → targeted search.

---

# 15. State Machine + Planner Hybrid

State machine enforces scientific gates.

Planner chooses flexible next action.

Example:
SEARCH → SCREENING → extraction is mandatory for SLR,
but screening may trigger another targeted search.

---

# 16. Agent Runtime

Standard contract:
name, version, input schema, output schema, tools, execute().

No arbitrary DB access.

---

# 17. Structured Agent Outputs

Critical outputs use structured schema.

Examples:
screening decision;
protocol;
review issue;
extraction;
orchestrator next action.

---

# 18. Prompt Registry

/prompts/
- research_director/
- protocol/
- screening/
- extraction/
- synthesis/
- writer/
- reviewer/

Each run records prompt version/model/input artifact versions.

---

# 19. LLM Gateway

LLMGateway:
- OpenAIProvider
- AnthropicProvider later
- GeminiProvider later

Common API:
generate
generate_structured
tool_call
embed

---

# 20. Initial LLM Strategy

OpenAI initially.

Core architecture does not depend directly on provider SDK.

---

# 21. Model Routing

Route by task:
- research reasoning;
- screening;
- extraction;
- manuscript synthesis;
- formatting.

Do not use highest-cost model everywhere.

---

# 22. LLM Privacy

Canonical state remains in our infrastructure.

Send only minimum scoped context.

Do not depend on provider-side conversation state.

---

# 23. Literature Provider Layer

AcademicProvider interface:
- search
- get_work
- get_by_doi
- get_references
- get_citations
- open-access locations where available.

---

# 24. Provider Roles

OpenAlex — discovery/citation graph.

Crossref — DOI/metadata authority.

Semantic Scholar — discovery/enrichment/citation graph.

---

# 25. Discovery Strategy

Search multiple declared providers.

Then:
normalize → merge → dedupe → verification.

For SLR, recall matters.

---

# 26. Record Normalization

Canonical WorkRecord:
- IDs;
- DOI;
- title;
- abstract;
- authors;
- year;
- venue;
- type;
- provider observations.

---

# 27. Source Identity Verification

Candidate DOI → Crossref/OpenAlex/S2 lookups → metadata consistency → verification result.

Identity verification does not equal study eligibility.

---

# 28. Database

PostgreSQL as authoritative scientific state.

---

# 29. pgvector

Use initially for vector retrieval without separate vector DB.

---

# 30. Retrieval Architecture

Hybrid:
metadata filters + full-text/keyword + vector similarity.

---

# 31. Project Memory

No giant DraftContext.

Project state uses structured entities:
Plan, Protocol, SearchRuns, Works, Studies, Evidence, Claims, Analyses, Manuscript, Reviews.

---

# 32. Context Builder

Agent receives only relevant context.

Example writer receives:
section objective, claims, evidence, citations, prior-section summary, style constraints.

---

# 33. Long-document Memory

Use section summaries + document summary + evidence retrieval.

No manual fixed string truncation.

---

# 34. Object Storage

PDF/full text/parsed docs/figures/plots/exports live in S3-compatible storage.

DB stores metadata/object keys.

---

# 35. Full-text Pipeline

PDF/HTML
→ ingestion
→ extraction
→ structural parsing
→ pages/sections
→ chunks
→ embeddings
→ evidence extraction.

Preserve page/section provenance.

---

# 36. Full-text Availability

Statuses:
open access;
user uploaded;
licensed;
abstract only;
unavailable.

---

# 37. Evidence Extraction Pipeline

Study
→ extraction schema
→ relevant passage retrieval
→ extraction agent
→ schema validation
→ consistency validation
→ evidence record.

---

# 38. Evidence Store

First-class evidence entity, not giant JSON summary.

---

# 39. Claim Store

Claim stores:
text, type, scope, supporting/contradictory evidence, confidence, manuscript locations.

---

# 40. Screening Engine

Parallelizable batch processing.

---

# 41. Screening Concurrency

Concurrency bounded by:
- LLM quota;
- SaaS plan;
- project priority;
- provider/system limits.

---

# 42. Statistical Engine

Not an agent.

packages/statistics:
- effect_sizes
- pooling
- heterogeneity
- sensitivity
- subgroup
- plots

---

# 43. Statistical Stack

NumPy  
pandas  
SciPy  
statsmodels  
+ explicit tested domain functions.

Validate critical results against trusted reference implementations/golden datasets.

---

# 44. Meta-analysis Data Flow

Extracted Outcomes
→ Compatibility Validator
→ Effect-size Calculator
→ EffectSize Records
→ Pooling Engine
→ MetaAnalysisResult
→ Forest Plot
→ Statistical Reviewer.

---

# 45. Reproducible Analyses

Persist:
- input study IDs;
- input values;
- transformations;
- effect measure;
- model;
- estimator;
- software version;
- results.

---

# 46. Manuscript Representation

Structured document:
Manuscript
→ title
→ abstract
→ sections
→ citations
→ claims
→ references.

Markdown is a rendering format, not canonical state.

---

# 47. Writing Pipeline

Approved outline
→ section plan
→ retrieve claims/evidence
→ writer
→ claim validation
→ citation validation
→ save section.

---

# 48. Reviewer Architecture

Reviewer receives structured snapshot and outputs ReviewIssue[].

---

# 49. Review Issue

Fields:
issue_id, reviewer_type, severity, category, description, manuscript location, evidence, suggested action, status.

---

# 50. Revision Engine

Issue → task → research/analysis/writing fix → recheck.

---

# 51. Audit/Event Layer

Append-only ProjectEvent:
PROJECT_CREATED, PLAN_GENERATED, PLAN_APPROVED, SEARCH_EXECUTED,
STUDY_INCLUDED, STUDY_EXCLUDED, EXTRACTION_UPDATED, META_ANALYSIS_RUN,
MANUSCRIPT_UPDATED, REVIEW_ISSUE_CREATED, REVIEW_ISSUE_RESOLVED.

---

# 52. Artifact Versioning

Protocol v1/v2 etc.

Downstream operations reference exact artifact versions.

---

# 53. Multi-Tenancy

Tenant-aware schema with organization/project scoping.

---

# 54. Tenant Isolation

MVP shared DB/shared schema with tenant keys.

Authorization enforced server-side.

---

# 55. Authentication

OAuth/OIDC provider.

Support email/Google; institutional SSO later.

---

# 56. Authorization

Roles:
OWNER
EDITOR
REVIEWER
VIEWER

---

# 57. Billing

Stripe provider, but entitlements maintained internally.

---

# 58. Usage Metering

Track:
- tokens;
- searches;
- papers;
- PDF parsing;
- screening;
- extraction;
- analysis;
- storage.

---

# 59. Cost Accounting

Cost per project/user/agent/provider.

---

# 60. Rate Limiting

Three levels:
- user;
- provider;
- system concurrency.

---

# 61. Cache

Cache:
- DOI metadata;
- provider records;
- embeddings;
- parsed document hashes.

Redis optional for fast ephemeral cache.

---

# 62. Idempotency

Long-running activities must be idempotent.

---

# 63. Progress Streaming

Use SSE initially.

---

# 64. Notifications

In-app initially; email later.

---

# 65. Observability

Trace:
Project Workflow
→ Workflow Step
→ Agent Run
→ LLM Request
→ Tool/API Call.

---

# 66. Logging

Structured logs:
request_id, project_id, workflow_id, agent_run_id, provider, duration, status.

Avoid logging manuscript/full-text contents by default.

---

# 67. Metrics

Workflow duration/failure/retry, API/LLM latency, tokens, search throughput, screening throughput, extraction errors, queue depth.

---

# 68. Scientific Metrics

Citation verification, screening conflicts, extraction corrections, unsupported claims, reviewer issues, statistical validation failures.

---

# 69. Security

TLS  
encryption at rest  
secret manager  
least privilege  
tenant authorization  
signed object URLs  
audit logs  
input validation

---

# 70. Secrets

No keys in repo.

Use environment/secret manager.

---

# 71. Upload Security

Validate type/size, malware scan, isolate parser, hash content.

---

# 72. Data Retention

Configurable retention for:
uploads, parsed text, traces, exports, deleted projects.

---

# 73. Backups

Postgres backups + PITR.

Object storage lifecycle/versioning.

---

# 74. MVP Deployment

CDN
→ Next.js
→ FastAPI
→ Postgres / S3 / Temporal / optional Redis
→ worker pools.

---

# 75. Container Strategy

Separate API/core/statistics/document images where dependencies differ.

---

# 76. Scaling Strategy

Scale API, research, AI, PDF, and statistics workers independently.

---

# 77. Background Batch Processing

Screening/extraction can batch/parallelize.

---

# 78. Testing Strategy

- Unit
- Integration
- Workflow
- Scientific Golden Tests
- Agent Evals
- E2E

---

# 79. Unit Tests

DOI normalization, dedupe, PRISMA counts, effect sizes, heterogeneity, citation formatting, permissions, usage.

---

# 80. Integration Tests

Provider adapters, LLM provider, object storage, Temporal, DB.

Use fixtures/mocks by default.

---

# 81. Agent Evals

Research Director, screening, extraction, claim support, protocol, reviewer evaluations.

---

# 82. Meta-analysis Golden Tests

Known expected:
effects, SE, weights, pooled estimate, CI, Q, I², τ².

---

# 83. End-to-End Fixtures

Curated research topics across domains.

---

# 84. OpenDraft Adoption

OpenDraft is not dependency.

Selective concepts/code:
- providers;
- metadata normalization;
- DOI verification;
- dedupe;
- citation rendering ideas;
- retry lessons;
- export patterns.

---

# 85. Explicit No-Reuse

Do not reuse as core:
- DraftContext;
- linear draft_generator;
- manual context slicing;
- fixed 19 agents;
- advisory-only QA;
- Gemini-centric setup;
- checkpoint.json.

---

# 86. API Boundary Examples

POST /projects  
GET /projects/{id}  
POST /projects/{id}/messages  
GET /projects/{id}/plan  
POST /projects/{id}/plan/approve  
GET /projects/{id}/protocol  
GET /projects/{id}/studies  
GET /projects/{id}/screening  
GET /projects/{id}/evidence  
GET /projects/{id}/analyses  
GET /projects/{id}/manuscript  
POST /projects/{id}/manuscript/review  
POST /projects/{id}/exports

---

# 87. Internal Modules

identity
projects
orchestration
agents
literature
fulltext
screening
evidence
synthesis
statistics
manuscript
reviews
documents
billing
audit

Logical modules; not microservices initially.

---

# 88. Error Taxonomy

USER_INPUT_ERROR  
PROVIDER_ERROR  
RATE_LIMIT  
TRANSIENT_NETWORK  
INVALID_AGENT_OUTPUT  
SCIENTIFIC_VALIDATION_ERROR  
PERMISSION_ERROR  
WORKFLOW_CONFLICT  
INTERNAL_ERROR

---

# 89. Retry Rules

Retry transient network/429/5xx/timeouts.

Do not blindly retry:
invalid protocol, permission denied, unsupported analysis, scientific validation failures.

---

# 90. Human Approval Signals

Temporal workflows may pause for approvals.

---

# 91. Cancellation

User can cancel search/screening/generation/review gracefully.

---

# 92. Reproducibility Bundle

Potential export:
protocol.json
search_runs.json
study_list.csv
screening_decisions.csv
evidence.csv
analysis_config.json
analysis_results.csv
references.bib
manuscript.docx

---

# 93. Local Development

Docker Compose:
Postgres, Temporal, Temporal UI, optional Redis, local S3-compatible storage.

---

# 94. CI/CD

GitHub Actions:
lint, type-check, unit, integration, scientific golden tests, web build, backend build, security scan, migration check.

---

# 95. Python Quality

ruff  
mypy  
pytest

---

# 96. TypeScript Quality

TypeScript strict  
ESLint  
frontend tests

---

# 97. Architecture Decision Records

/docs/adr/

ADR examples:
Temporal, PostgreSQL, pgvector, provider abstraction, modular monolith.

---

# 98. Locked MVP Decisions

Frontend → Next.js/TypeScript  
Backend → Python/FastAPI  
Workflow → Temporal  
DB → PostgreSQL  
Vector → pgvector  
Files → S3-compatible  
Primary LLM → OpenAI behind adapter  
Academic → OpenAlex/Crossref/S2  
Statistics → deterministic Python  
Documents → Pandoc

---

# 99. Explicit Non-Decisions

Not yet lock:
cloud vendor, managed DB vendor, Temporal Cloud vs self-hosted, auth vendor, exact model IDs, pricing tiers, CDN.

---

# 100. Implementation Order

1. project/domain foundation
2. PostgreSQL/migrations
3. auth
4. Temporal
5. LLM Gateway
6. academic providers
7. Research Director
8. search pipeline
9. normalization/dedupe
10. screening
11. full text
12. extraction
13. retrieval
14. synthesis
15. manuscript
16. reviewers
17. meta-analysis
18. export
19. billing/metering
20. hardening

---

# 101. First Vertical Slice

User creates project
→ idea
→ Research Director
→ Research Plan
→ multi-provider search
→ normalize
→ dedupe
→ literature list.

---

# 102. Second Vertical Slice

Protocol
→ screening
→ included studies
→ evidence extraction
→ evidence matrix.

---

# 103. Third Vertical Slice

Evidence
→ synthesis
→ claim graph
→ manuscript
→ reviewer
→ revision.

---

# 104. Fourth Vertical Slice

Quantitative SLR
→ outcome extraction
→ effect size
→ pooling
→ forest plot
→ statistical reviewer.

---

# 105. Architecture North Star

Not:
Chat → LLM → Article.

Instead:
Research Project + Evidence + Workflow + Manuscript,
coordinated by Scientific Orchestrator + agents + deterministic tools.

---

# 106. Final Architecture Statement

RanahResearch is a durable, evidence-centric agentic research platform.

PostgreSQL stores authoritative state.
Temporal coordinates execution.
Agents reason over scoped context.
Academic providers supply literature.
Evidence Store grounds claims.
Deterministic statistical engine runs meta-analysis.
Reviewer Council produces structured issues.
Revision loop resolves them before author review.

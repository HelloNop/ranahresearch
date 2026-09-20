# OpenDraft Adoption & Migration Specification v0.1

**Source:** `federicodeponte/opendraft`

---

# 1. Objective

OpenDraft is:
- reference implementation;
- engineering donor;
- source of patterns/lessons.

OpenDraft is not:
- production base;
- runtime dependency;
- orchestration foundation.

Use:
OpenDraft → inspect → define our contract → selectively port/adapt → test → integrate.

---

# 2. Adoption Categories

PORT — substantial implementation reused with limited changes.  
ADAPT — algorithm/logic retained, interfaces/architecture rewritten.  
REFERENCE — concept/pattern only.  
REJECT — intentionally not used.

---

# 3. Adoption Summary

Crossref client → ADAPT  
OpenAlex client → ADAPT  
Semantic Scholar client → ADAPT  
Base API client → REFERENCE  
Multi-source DOI confirmer → ADAPT  
Citation deduplication → ADAPT  
Citation database → REWRITE  
Citation quality filter → REFERENCE only  
Query Router → REFERENCE  
Citation claim verifier → REFERENCE  
Citation compiler → PARTIAL ADAPT  
Stable citation IDs → ADAPT  
Agent runner → REJECT  
Gemini wrapper → REJECT  
Concurrency config → REFERENCE  
Checkpoint implementation → REJECT  
Export/PDF fallback → ADAPT  
DraftContext → REJECT  
draft_generator → REJECT  
fixed phases → REJECT  
quality gate → REJECT  
OpenDraft prompts/agents → REFERENCE concepts, rewrite contracts/prompts.

---

# 4. Academic Provider Layer

Relevant OpenDraft:
engine/utils/api_citations/
- base.py
- crossref.py
- openalex.py
- semantic_scholar.py
- multi_source.py
- query_router.py
- orchestrator.py

Target:
packages/literature/
- providers/base.py
- providers/crossref.py
- providers/openalex.py
- providers/semantic_scholar.py
- normalization.py
- deduplication.py
- verification.py
- discovery.py

---

# 5. Crossref

Adapt:
- /works search;
- DOI lookup;
- title/authors/year;
- DOI;
- journal/publisher;
- volume/issue/pages;
- JATS abstract cleanup;
- source-type mapping.

Rewrite search to:
async + pagination + filters + full result set.

---

# 6. OpenAlex

Adapt:
- abstract inverted-index reconstruction;
- DOI;
- authors;
- year;
- venue;
- citation count;
- work type;
- DOI lookup.

Extend:
search/get_work/get_by_doi/get_references/get_citations.

---

# 7. Semantic Scholar

Adapt:
- Graph API;
- DOI identifier syntax;
- external IDs;
- authors;
- venue;
- citations;
- abstract;
- publication types.

Rewrite for paginated result collections.

---

# 8. AcademicProvider Interface

async search()  
async get_work()  
async get_by_doi()  
async get_references()  
async get_citations()

Providers declare capabilities.

---

# 9. base.py

Do not port wholesale.

Useful concepts:
retry, exponential backoff, rate limiting, errors, URL safety.

Target:
async ProviderHTTPClient with tracing, metrics, quotas, circuit breaker.

---

# 10. Multi-source Verification

Adapt concept to SourceVerificationService.

Output:
- verification_status;
- verified_by;
- metadata_conflicts;
- identity_confidence;
- verified_at.

---

# 11. Critical SLR Change

Never hard-delete/exclude a record only because DOI is not confirmed by two databases.

Identity confidence != eligibility.

SLR eligibility comes from protocol/screening.

---

# 12. Deduplication

Adapt:
- DOI;
- URL/external IDs;
- normalized title;
- fuzzy title.

---

# 13. Dedup Rewrite

Avoid broad O(n²) comparison for large corpora.

Use blocking:
1. DOI
2. external IDs
3. exact normalized title
4. title/year/first-author blocks
5. fuzzy similarity
6. uncertain resolution

Persist DuplicateGroup/Decision.

---

# 14. Record Dedup vs Study Linking

Record dedup = same publication.

Study linking = multiple publications from same underlying study.

Both required.

---

# 15. Citation Database

Do not use `Citation` as canonical domain entity.

Use:
WorkRecord, Study, SourceMetadata, Evidence, Outcome, Claim.

---

# 16. Stable IDs

Keep concept of stable internal IDs.

Use canonical UUID/ULID-style IDs plus optional human aliases.

---

# 17. Citation Quality Filter

Do not port as hard filter.

Convert to validation warnings:
MISSING_AUTHOR, MISSING_YEAR, SUSPICIOUS_DOI, LOW_METADATA_CONFIDENCE, TOPIC_MISMATCH.

Eligibility remains protocol-driven.

---

# 18. Author Validation

Potential metadata problems become warnings, not automatic scientific exclusion.

---

# 19. Query Router

Reference only.

For SLR:
Protocol → declared databases → query all required providers.

Fallback-chain logic is unsuitable for reproducible SLR.

---

# 20. Citation Claim Verification

Keep distinction:
source exists != source supports claim.

---

# 21. Evidence Verification Upgrade

Replace topic-level relevance with ClaimEvidenceVerifier using extracted evidence/passages.

Verdicts:
SUPPORTED
PARTIALLY_SUPPORTED
CONTRADICTED
UNCERTAIN
UNSUPPORTED.

---

# 22. Citation Compiler

Keep deterministic source-reference replacement concept.

Reject automatic `{cite_MISSING:topic}` research during compile.

Missing citation triggers validation/orchestrator task instead.

---

# 23. Citation Formatting

Prefer mature CSL-based formatting.

OpenDraft formatting can provide fallback/reference tests.

---

# 24. Agent Runner

Reject implementation.

Build AgentRuntime + LLMGateway.

---

# 25. Agent Runner Lessons

Retain:
- retry;
- structured validation;
- usage/token capture;
- prompt loading;
- logging.

---

# 26. Concurrency Config

Reference only.

Replace with ProviderQuotaManager + Temporal queues.

---

# 27. Checkpoint

Reject checkpoint.json implementation.

Replace:
Temporal history + PostgreSQL state + artifact versions.

---

# 28. Export

Adapt:
- Pandoc;
- PDF fallbacks;
- DOCX;
- LaTeX;
- metadata normalization.

Target DocumentExportService worker.

---

# 29. Export Changes

Never invent author/institution/advisor metadata.

---

# 30. DraftContext

Reject.

Use relational persistent project state.

---

# 31. draft_generator.py

Reject fixed linear flow.

Use Scientific Orchestrator + Temporal + methodology state machine.

---

# 32. Agent Role Mapping

Scout → Literature Search  
Scribe → Evidence Extraction  
Signal → Synthesis/Gap  
Architect → Research Director / Manuscript Planner  
Crafter → Manuscript Writer  
FactCheck → Claim-Evidence Reviewer  
Referee → Scientific Reviewer

No fixed OpenDraft hierarchy.

---

# 33. Quality Gate

Reject old document-shape-focused gate.

Build ScientificQualityGate:
method compliance, search integrity, screening, evidence, claims, RoB, statistics, reviews.

---

# 34. Target Package Mapping

packages/
literature/providers/*
literature/normalization.py
literature/deduplication.py
literature/verification.py
literature/discovery.py
evidence/extraction.py
evidence/verification.py
evidence/retrieval.py
citations/resolver.py
citations/formatter.py
documents/export.py

---

# 35. Porting Procedure

1. Identify OpenDraft source file/functions.
2. Define behavior to retain.
3. Create tests.
4. Define new interface.
5. Port relevant logic.
6. Remove DraftContext/Gemini/CLI/global-state coupling.
7. Add async/tracing/metering/quotas/durable retry.
8. Run tests.

---

# 36. Provider Migration Example

Old:
search_paper(query) -> Paper

New:
async search(query, filters, cursor) -> SearchPage[ProviderWork]

Provider returns neutral ProviderWork, not Citation.

---

# 37. Canonical Metadata

No provider is blindly authoritative for every field.

Store provider observations and conflict status.

---

# 38. Tests to Adapt

- API parsing
- DOI normalization
- dedupe
- citation formatting
- invalid metadata cases

---

# 39. Provider Fixture Strategy

tests/fixtures/
- crossref
- openalex
- semantic_scholar

Cases:
normal, missing DOI, many authors, missing abstract, preprint, conference, Unicode, multiple identifiers.

---

# 40. Licensing

OpenDraft MIT.

If substantial code is reused:
- retain required copyright/license notice;
- include THIRD_PARTY_NOTICES.md;
- optionally annotate directly adapted files.

---

# 41. Explicit No-Copy List

Do not copy:
- fictional academic metadata defaults;
- Gemini-specific setup;
- global mutable config;
- DraftContext;
- linear generator;
- fixed 19 agents;
- manual context truncation;
- checkpoint.json;
- weak QA heuristics;
- SLR hard exclusions from metadata/topic heuristics.

---

# 42. First Adoption Milestone

AcademicProvider
→ Crossref/OpenAlex/S2
→ Work normalization
→ record merge
→ dedupe
→ verification.

---

# 43. Second Adoption Milestone

SearchRun
→ SearchQuery
→ Provider execution
→ WorkRecord
→ dedupe
→ verification
→ Research Director/Search Strategist integration.

---

# 44. Definition of Done

- no OpenDraft runtime dependency;
- async providers;
- pagination;
- raw provenance;
- auditable dedupe;
- verification separated from eligibility;
- tests;
- licensing;
- OpenDraft can change/disappear without breaking product.

---

# 45. Final Decision

OpenDraft is an engineering donor, not the product foundation.

Take:
1. academic provider knowledge
2. normalization ideas
3. DOI/source verification concepts
4. dedupe logic
5. stable source identity idea
6. retry/rate-limit lessons
7. export patterns

Build:
1. Scientific Orchestrator
2. Agent Runtime
3. Research Project State
4. Protocol Engine
5. SLR Engine
6. Screening Engine
7. Study Model
8. Evidence Store
9. Claim Graph
10. Meta-analysis Engine
11. Reviewer Council
12. Revision Loop
13. SaaS infrastructure

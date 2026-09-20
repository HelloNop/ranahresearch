# Traceable evidence layer: implementation report

Date: 2026-09-20. Scope: EPIC-023 through EPIC-029 and functional full-text
screening. EPIC-013 through EPIC-022 were reused. No synthesis, claim graph,
manuscript, or meta-analysis pooling was added.

## Repo health

At handoff, the backend suite had 199 passing tests and four failing extraction
tests. All four shared a JSONB `null` versus SQL `NULL` constraint mismatch.
The corrected evidence mapping uses SQL `NULL` for missing values. The final
verification commands and counts are recorded below. The existing Starlette
and AnyIO deprecation warnings do not affect the tests.

## Epic status

| Epic | Status | Delivered |
| --- | --- | --- |
| EPIC-023 Full-text Acquisition | COMPLETE | User PDF upload, provider-declared open-access retrieval, S3-compatible storage, SHA-256 deduplication, acquisition events and honest unavailable states. |
| EPIC-024 PDF / Document Parsing | COMPLETE | Parser boundary, page and section structure, stored chunks, parser provenance, warnings and failure state. OCR and embeddings remain optional. |
| EPIC-025 Evidence Extraction | COMPLETE | Protocol/framework-specific schema, study-level multi-report retrieval, extractor contract, reported/derived/missing states and exact chunk provenance. |
| EPIC-026 Evidence Validation | COMPLETE | Deterministic numeric checks, independent reviewer, conflict events and version-preserving human corrections. |
| EPIC-027 Evidence Matrix UI | COMPLETE | Full-text queue, study links, dynamic matrix, filters, study/source detail, corrections, progress and basic appraisal view. |
| EPIC-028 Study Linking | COMPLETE | Separate Study and WorkRecord identities, deterministic registration matching, conservative StudyLinker, human link decisions and preserved publications. |
| EPIC-029 Risk-of-Bias Foundation | COMPLETE | Design-aware tool selection, versioned assessment/domain rows, tentative agent proposals, exact passage checks and human approval API. Full signalling questions are deferred. |

## Full text and screening

`FullTextAcquisitionService` accepts user-uploaded PDFs and provider metadata
that explicitly identifies open-access locations. The remote path runs in a
Temporal activity. It does not bypass access controls or represent inaccessible
articles as read. Bytes are size-checked, PDF-validated, hashed, and stored in
S3-compatible object storage under project/work/hash keys. Repeated uploads
reuse the blob and record an upload attempt. The scanner hook currently has no
deployed scanner.

`FullTextParsingWorkflow` reads an asset and persists `ParsedDocument` and
`DocumentChunk` records with page, section, text and parser metadata. References
are excluded from passage retrieval. Malformed PDFs retain the original asset
and enter a failure state. OCR is not enabled by default; table extraction is
best effort. The web queue exposes upload, acquisition, parsing and full-text
screening states separately.

Full-text screening reuses `screening_agent` prompt v2 and the existing
protocol/criterion output. `FULL_TEXT_UNAVAILABLE` is a system retrieval fact.
The final included corpus requires an effective **FULL_TEXT INCLUDE** for the
current protocol. Title/abstract inclusion alone cannot start extraction.

## Study and evidence

`Study` and `StudyWork` link reports without deduplicating away publications.
Registration identifiers provide deterministic matches. Ambiguous cases go to
`StudyLinker`; a human can LINK, KEEP_SEPARATE or leave UNCERTAIN. Link decisions
and publication records remain available for audit.

The extraction schema is tied to a protocol version and question framework.
PICO/PICOS includes comparator and quantitative effect slots; other frameworks
omit those intervention-specific slots. A protocol change creates a new schema
version. The extractor retrieves bounded passages per field across all reports
of the study. Extracted values retain report, document, chunk, page, section,
exact quote and agent run IDs. Missing fields are explicit SQL-null values with
reasons. Derived values require a derivation. Re-running the same schema does
not create duplicate current evidence. A new schema supersedes prior current
values while retaining their history.

Deterministic validation checks count ranges, arm totals, event totals,
dispersion, percentages and confidence-interval ordering. `EvidenceReviewer`
independently checks values against source passages and records VERIFIED,
PARTIAL, CONFLICT or UNVERIFIED findings without rewriting extraction.
Corrections append a new value and audit event, preserving the AI value.

The Evidence Workspace displays schema-driven study rows, status and outcome
filters, linked publications, the exact source quote and page, verification
history, and a correction form. It also shows extraction progress and the
full-text screening boundary. Wide matrices scroll within their table area on
phones; the page itself stays within the viewport.

## Risk of bias

The versioned foundation registry maps `RCT` to `ROB_2` and
`QUASI_EXPERIMENTAL` to `ROBINS_I`. Other designs remain unsupported until a
fit-for-purpose tool is implemented. A human records study design with an
audited reason. `RiskOfBiasAgent` receives only retrieved methods/results
passages, the selected tool and its domain codes. Assessed domains require an
exact quote and passage ID. Unsupported or unreported domains remain
UNASSESSED, which prevents an overall risk judgement. Assessments and domains
are immutable versions. Human approval creates another version and validates
that each domain cites a linked publication and exact page quote.

These `foundation-1` domain summaries are not full RoB 2 or ROBINS-I
signalling-question implementations. Appraisal proposals need human review.

## Persistence and workflows

Migrations: `d34a95117685` (full text and parsed documents),
`7b834e827c1d` (studies and links), `5baf40062978` (extraction and
verification), and `926c9833b614` (risk-of-bias history).

Temporal workflows: `FullTextAcquisitionWorkflow`, `FullTextParsingWorkflow`,
`StudyLinkingWorkflow`, `FullTextScreeningWorkflow`,
`EvidenceExtractionWorkflow`, and `RiskOfBiasWorkflow`. External retrieval,
parsing and agent calls run in activities. Extraction commits one study per
transaction, preserving completed studies after a later failure.

## Agent contracts

| Agent | Prompt | Structured input/output | Tools | Routing |
| --- | --- | --- | --- | --- |
| StudyLinker | `study_linker/v1` | Work metadata/snippets/signals → conservative link decision and evidence | `literature.read_metadata`, limited `fulltext.read` | STANDARD |
| EvidenceExtractor | `evidence_extractor/v1` | Study, schema, question, passages → extracted/missing/uncertain fields | `fulltext.read`, `protocol.read` | HIGH_PRECISION_EXTRACTION |
| EvidenceReviewer | `evidence_reviewer/v1` | Values, schema labels, independent passages → per-value verdict | `fulltext.read`, `evidence.read` | HIGH_PRECISION_EXTRACTION |
| RiskOfBiasAgent | `risk_of_bias_agent/v1` | Study design, tool domains, passages → domain/overall proposal | `fulltext.read`, `study.read` | HIGH_PRECISION_EXTRACTION |

Each agent returns structured output through AgentRuntime and LLMGateway;
none can mutate domain tables directly. Domain services persist accepted
outputs and their AgentRun provenance.

## Verification

Final verification on 2026-09-20:

| Command | Result |
| --- | --- |
| `uv run pytest -q` | 208 passed, with two dependency deprecation warnings. |
| `uv run ruff check .` | Passed. |
| `uv run ruff format --check .` | 192 files already formatted. |
| `npm run lint` | Passed. |
| `npm run typecheck` | Passed. |
| `npm run build` | Production build completed successfully. |
| `npm test --workspace @ranahresearch/web` | 3 Playwright tests passed, including the mobile evidence workspace. |
| `git diff --check` | Passed. |

Alembic reports one head, `926c9833b614`, on a linear seven-revision chain.
The backend suite creates a fresh `ranahresearch_test` database and upgrades it
through that real migration chain before running tests, so the passing suite
also verifies a clean migration to the current schema.

## Scientific invariants and remaining work

WorkRecord and Study remain separate. Title/abstract INCLUDE is never final
inclusion. Evidence values cite the source report and page/chunk when reported;
missing values are never filled from model guesses. Risk-of-bias tool selection
is tied to an explicit design classification.

The current parser does not run OCR, embeddings are optional, and no malware
scanner is deployed. RoB 2 and ROBINS-I signalling questions and formal
aggregation rules are future work. These limits do not block starting
EPIC-030 evidence synthesis work, but synthesis must use verified evidence and
surface unresolved conflicts. EPIC-031 through EPIC-039 remain unimplemented
and are outside this batch.

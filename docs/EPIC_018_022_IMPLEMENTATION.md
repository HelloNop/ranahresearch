# Protocol and Title/Abstract Screening: implementation report

Date: 2026-09-20. Scope: finish blocking discovery UI gaps and implement
EPIC-019 through EPIC-022 for the first production title/abstract stage.
EPIC-013 through EPIC-017 were not reimplemented.

## Repo health

Before changes: 127 backend tests passed; frontend ESLint and TypeScript passed.
After changes: 148 backend tests and 2 browser scenarios passed. Ruff, format
checks, mypy, ESLint, TypeScript, and Next.js production build passed.
Two existing Starlette/httpx/AnyIO deprecation warnings remain.
Migration `85bd64d6c81a` was applied to the local database; `alembic check`
reported no new upgrade operations. No manual database edits are required.

## EPIC status

| Epic | Status | Accepted scope |
|---|---|---|
| EPIC-018 | COMPLETE | Blocking discovery entry, navigation, filters, pagination and queued-operation recovery resolved. |
| EPIC-019 | COMPLETE | Versioned protocol, agent generation, provenance, explicit approval and amendment API. |
| EPIC-020 | COMPLETE | Typed criteria, version binding, deterministic evaluation and human-readable value editor. |
| EPIC-021 | COMPLETE | Title/abstract stage, durable bounded batches, immutable decisions, override, counts, partial retry. FULL_TEXT execution remains deferred. |
| EPIC-022 | COMPLETE | Protocol and screening workspaces, recommendations, rationale, history, filters, progress and partial states. |

These statuses use this task's acceptance boundary. They do not claim the
original roadmap's full-text screening or all of milestone M2 is finished.

## EPIC-018 gap closure

Repository inspection found that the existing page could create projects but
could not reopen an existing project. It had no project selector. Literature
filters changed local state but did not fetch when no operation was active.
The literature list stopped at the API's default first 100 records. Operation
polling refreshed the project endpoint, bypassing the operation endpoint's
persisted-PENDING dispatch recovery.

Added existing-project navigation, filter-triggered fetch, previous/next
literature pages and stable ID tie-breaking in API pagination. Polling now calls
the operation endpoint, surfaces queued Temporal errors, and then refreshes
artifacts. The existing plan/framework/strategy display and provider partial
states remain in place. Discovery links directly to Protocol & screening.
The existing visual style was retained. The button accent was darkened slightly
for a measured 5.05:1 text contrast ratio.

Antislop design read: retain the existing paper background, serif reading text,
green scientific labels and warm action accent. ENERGY 1, RHYTHM 2, MOTION 1.
The focal point is the scientific artifact or selected publication; layout
variation distinguishes reading, queue navigation and decisions. No new assets,
decorative animation or visual redesign were introduced. Browser interaction,
desktop/mobile screenshots and focus/contrast checks cover this change's gate.

## Protocol

`ReviewProtocol` is a relational scientific artifact with project, plan and
framework foreign keys, immutable versioned content, research-question snapshot,
background, objective, method, strategies, risk-of-bias and meta-analysis plans,
actual information sources, assumptions, uncertainties, AgentRun provenance,
creation and approval attribution. Allowed statuses are DRAFT, PROPOSED,
APPROVED, SUPERSEDED and REJECTED.

Generation creates PROPOSED v1 through `ProtocolWorkflow`. `protocol_agent` v1
uses `run_agent` (the existing AgentRuntime entry point), scoped ContextBuilder,
LLMGateway and strict Pydantic structured validation with bounded schema repair.
The prompt forbids fabricated registration, outcome-driven criteria, hidden
question changes, and post-hoc justification. Code checks preserve review method
and actual discovery source identities. The question/framework references come
from the approved plan rather than model-generated replacements. Missing
information is represented in structured uncertainties, which require explicit
human acknowledgement before approval. These controls cannot prove every
free-text model statement true; human protocol review remains necessary.

Approval accepts only the current PROPOSED protocol aligned with the current
approved plan. Material edits create a new PROPOSED version, supersede the old
version, and append field-level amendments with old/new values, actor, timestamp,
reason and stage classification. Criteria are copied to new version-specific
rows. Database triggers reject content updates and deletion of old protocols,
criteria, amendments and screening decisions.

API routes, all project/tenant scoped:

- `POST /projects/{id}/protocol/generate`
- `GET /projects/{id}/protocol`
- `GET /projects/{id}/protocol/versions`
- `POST /projects/{id}/protocol/{protocol_id}/approve`
- `POST /projects/{id}/protocol/{protocol_id}/revise`
- `GET /projects/{id}/eligibility-criteria`

Protocol views include the exact referenced framework, including historical
versions, rather than substituting the project's latest framework.

## Eligibility criteria

Dimensions: POPULATION, INTERVENTION, EXPOSURE, COMPARATOR, OUTCOME, STUDY_DESIGN,
SETTING, PUBLICATION_TYPE, YEAR, LANGUAGE, COUNTRY, PEER_REVIEW and OTHER.
Operators and values are validated together: semantic MATCHES takes a typed
`description`; YEAR takes strict integer GTE/LTE/EQ; LANGUAGE, PUBLICATION_TYPE
and COUNTRY take nonempty IN/NOT_IN string lists; PEER_REVIEW takes boolean EQ.
INCLUDE is a requirement; EXCLUDE is a prohibition. Each criterion has a reason
and priority and belongs to exactly one protocol version.

The deterministic evaluator handles year, language and publication type. The
worker trusts these fields only when at least two distinct providers agree on
the canonical value and there are no conflicting observed values. Missing,
conflicting or single-source fields return UNKNOWN. Identity verification does
not itself establish field-level trust. Semantic reasoning stays in the agent.
Known deterministic results must be preserved by the agent output validator.
The UI shows readable dimensions, values and reasons. Revision permits editing
criterion values and protocol sections without exposing raw JSON.

## Screening

`TitleAbstractScreeningWorkflow` repeatedly prepares the next unscreened batch,
runs the agent in an Activity, persists each record, and calculates progress.
`SCREENING_BATCH_SIZE` defaults to 10 and is bounded to 1..100. Calls are
sequential within a batch, so there is no unbounded LLM fan-out. Activities retry
up to three attempts with Temporal backoff. On exhausted failure the operation
becomes PARTIAL; prior successful records remain committed. A retry command
starts a new operation for remaining records, reusing valid decisions for the
same protocol. A new protocol version gets a separate decision namespace and
therefore re-screens the corpus.

A screening round reuses `WorkflowRun`; no additional round table is needed.
Its durable details store protocol ID/version, TITLE_ABSTRACT stage, canonical
work-ID snapshot, records_total and batch size. Status/start/completion are the
existing workflow columns. Corpus selection excludes noncanonical members of
resolved MERGE groups; unresolved potential duplicates remain visible.

`screening_agent` v1 uses the runtime/gateway and versioned prompt. It receives
one title/abstract, metadata, protocol version and bound criteria. It has only
`protocol.read` and `literature.read_metadata` scopes. No search, full-text,
protocol mutation, evidence write or manuscript write is allowed.

Every assessment must refer to exactly one supplied criterion; every supplied
criterion must be assessed. Evidence must be an exact input-text span or a
preserved trusted deterministic assessment. EXCLUDE requires a standardized
reason and an evidenced failed criterion matching its dimension. Fabricated
spans and contradictory INCLUDE-with-FAIL output are rejected. Missing abstract
alone is not an exclusion condition. The prompt prioritizes recall and UNKNOWN
or UNCERTAIN when evidence is insufficient.

Reason registry: WRONG_POPULATION, WRONG_INTERVENTION, WRONG_EXPOSURE,
WRONG_COMPARATOR, WRONG_OUTCOME, WRONG_STUDY_DESIGN, WRONG_SETTING,
WRONG_PUBLICATION_TYPE, OUTSIDE_DATE_RANGE, WRONG_LANGUAGE,
NOT_PRIMARY_RESEARCH and OTHER. FULL_TEXT_UNAVAILABLE is not accepted here.

Decisions persist project/work, optional study reference, stage, exact protocol
ID/version, round, decision, reason, rationale, confidence, reviewer/actor,
AgentRun, criterion assessments, evidence spans and timestamp. A partial unique
index makes AI decisions idempotent per protocol/work/stage. No update/delete
endpoint exists; database triggers also reject mutation.

Effective-state resolution is scoped to protocol ID and stage. The latest HUMAN
decision wins over AI/SYSTEM, even if an AI row is newer. With no human decision,
the latest AI/SYSTEM event applies. Human overrides append new events and
project audit events. Earlier AI recommendations and older protocol versions
remain visible in screening history.

API routes:

- `POST /projects/{id}/screening/title-abstract/start`
- `GET /projects/{id}/screening/title-abstract` with filter/offset/limit/round_id
- `GET /projects/{id}/screening/title-abstract/progress` with optional round_id
- `POST /projects/{id}/works/{work_id}/screening-decisions`
- `GET /projects/{id}/works/{work_id}/screening-history`
- `GET /projects/{id}/literature?work_id=...` for record metadata/provenance

Counts are total, screened, include, exclude, uncertain, conflict and remaining
for the selected round's corpus and protocol, not final PRISMA counts.

## UI and scientific integrity

The existing `/` research workspace adds project navigation and a Protocol &
screening tab. `screening-workspace.tsx` provides generation, uncertainty
acknowledgement, approval, section/value revision, protocol version history,
queue, title/authors/year/journal/DOI/abstract, AI rationale/confidence/criterion
assessments, human Include/Exclude/Uncertain, standardized exclusion selector,
optional note, provenance/history disclosure, pagination and filters.

Starting AI screening returns an async operation and polling displays partial
results while later records continue. A protocol-version mismatch is visible.
PARTIAL exposes a retry action for remaining records. Desktop uses three
columns; narrow screens stack the queue, record and criteria/actions.

**Title/Abstract INCLUDE is not treated as final inclusion.** No Study creation,
full-text retrieval/parsing, extraction, evidence matrix, study linking, appraisal
execution or manuscript generation was added. FULL_TEXT exists only as a domain
stage boundary. UI labels explicitly identify passage to future Full-text Review.

## Tests and reproducible commands

Run PostgreSQL and Temporal as in the existing local infrastructure setup.
Tests use a dedicated test database and fake LLM/provider fixtures.

```sh
uv run --all-packages --locked pytest
uv run --all-packages --locked ruff check .
uv run --all-packages --locked ruff format --check .
uv run --all-packages --locked mypy apps/api/src packages tests scripts workers/orchestration/src
npm run lint
npm run typecheck
npx playwright install chromium
npm run test --workspace @ranahresearch/web
npm run build
uv run --all-packages --locked alembic -c packages/domain/alembic.ini upgrade head
uv run --all-packages --locked alembic -c packages/domain/alembic.ini check
```

The 21 additional backend cases cover typed criteria, GTE/LTE/IN/NOT_IN,
missing/untrusted metadata, protocol persistence and AgentRun linkage, approval
and invalid transitions, versioning, exact historical provenance, 100 canonical
works, count consistency, immutable AI/HUMAN history, database mutation rejection,
transient retry, partial failure/resume, clearly eligible/wrong population/
insufficient abstract/wrong design fixtures, fabricated-evidence rejection and
resolved-duplicate exclusion from the corpus.
An additional amendment fixture verifies adding YEAR GTE 2020 before screening,
preserving v1 criteria and recording PRE_SEARCH_CHANGE provenance.

Two browser scenarios exercise project reopening, idle literature filters,
protocol generation/rendering, criteria/framework display, uncertainty gate,
approval, revision submission, screening load, AI recommendation, human
include/exclude/uncertain, history, progress polling, filtering, partial retry
and mobile overflow. API responses are mocked in browser tests; the backend
vertical tests separately use real PostgreSQL and Temporal with fake LLMs.
This is implementation validation, not measured live-model screening recall.

## Remaining boundaries and readiness

- Live-provider semantic accuracy/recall benchmarking remains necessary before
  trusting autonomous screening in a real scientific review. Human review and
  overrides are available now; fixture outputs do not establish model accuracy.
- Local token authentication remains the existing convention; managed sign-in
  is outside this slice. Start/restart the API and orchestration worker with the
  updated code and normal environment after applying migrations.
- The criterion UI edits existing values. Adding/removing criteria and changing
  dimensions/operators is supported by the structured revision API; a richer
  criterion editor is deferred.
- Round corpus snapshots and effective-state queries currently load project
  decision lists in memory. Benchmark and move to SQL window/paged queries for
  very large corpora. No large-corpus performance claim is made.
- Cancellation, independent dual screening, adjudication and full-text stage
  execution remain outside this task's first-stage acceptance boundary.
- Existing deprecation warnings remain; no unrelated dependency cleanup.

The repository is ready for EPIC-023 Full-text Acquisition and EPIC-024 Document
Parsing as the next implementation steps. EPIC-025 Evidence Extraction,
EPIC-026 Evidence Validation, EPIC-027 Evidence Matrix UI, EPIC-028 Study Linking
and EPIC-029 Risk-of-Bias Foundation have a versioned protocol/screening handoff,
but their runtime workflows are not implemented and depend on their upstream
epics. None of EPIC-023 through EPIC-029 was started here.

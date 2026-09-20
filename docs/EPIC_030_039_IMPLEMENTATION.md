# EPIC-030–039 Implementation Record

Status: COMPLETE for the narrative/descriptive manuscript slice. Statistical pooling and outcome-level meta-analysis remain intentionally deferred to EPIC-040–048.

## Repo health

The baseline before this batch was 208 passing backend tests and all existing frontend checks. The completed implementation now passes:

- `make check` — 215 passed, 2 dependency deprecation warnings;
- `uv run --all-packages --locked alembic -c packages/domain/alembic.ini check` — no upgrade operations detected;
- `make build` — all Python distributions and the Next.js production build;
- `npm --prefix apps/web run test` — 4 Playwright tests passed.

EPIC-023 through EPIC-029 were inspected and remain complete; they were not reimplemented.

## EPIC status

| Epic | Status | Delivered |
| --- | --- | --- |
| EPIC-030 | COMPLETE | Versioned synthesis, themes, findings, contradictions, corpus-scoped gaps, method selection, and evidence links |
| EPIC-031 | COMPLETE | Persistent claim graph, evidence/study links, verification records, qualification and provenance |
| EPIC-032 | COMPLETE | Versioned manuscript, sections, claim locations, citation mappings, immutable completed versions |
| EPIC-033 | COMPLETE | Structured plan with objectives, claims, evidence/citation requirements, and word budgets |
| EPIC-034 | COMPLETE | Section-scoped writer context, deterministic methods/results facts, internal citation markers |
| EPIC-035 | COMPLETE | WorkRecord-based APA 7/Vancouver resolver and Markdown/DOCX/PDF/LaTeX renderers |
| EPIC-036 | COMPLETE | Six specialized reviewers returning structured ReviewIssues |
| EPIC-037 | COMPLETE | Revision tasks, cloned versions, section-local revision, re-review, blocking gate, author dismissal |
| EPIC-038 | COMPLETE | Synthesis, claim, manuscript, evidence/citation inspector, review panel, responsive workspace |
| EPIC-039 | COMPLETE | Provenanced Markdown, DOCX, PDF, and LaTeX export from one structured source |

## Synthesis and claim graph

`EvidenceSynthesis` owns a version, protocol/question, method (`NARRATIVE_SYNTHESIS`, `THEMATIC_SYNTHESIS`, or `DESCRIPTIVE_SYNTHESIS`), status, limitations, and confidence notes. Themes, findings, contradictions, and `ResearchGap` rows retain structured evidence references. Contradictions require both supporting and opposing evidence; gaps require language scoped to the reviewed corpus. Risk-of-bias is included in the synthesis context and confidence is not treated as a statistical estimate.

Claims are persisted separately from evidence. The trace is:

```text
Claim → ClaimEvidenceLink → Evidence → Study → WorkRecord
```

`ClaimVerification` records `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`, `UNCERTAIN`, or `UNSUPPORTED`, the reason, qualification, confidence, and agent run. Causal candidates require RCT/quasi-experimental support; unsupported candidates are rejected and never enter manuscript writing. Claim and plan reuse is scoped to the active synthesis version.

## Manuscript pipeline

`ManuscriptGenerationWorkflow` gates readiness, generates synthesis, builds/verifies claims, plans sections, writes sections incrementally, resolves citations, runs the reviewer council, applies at most two automatic revision rounds, and transitions only to `READY_FOR_AUTHOR_REVIEW` when blocking issues are absent. Each external LLM call is an activity and usage is recorded through `AgentRun`/`UsageEvent`.

Methods and Results receive deterministic facts from persisted protocol, search, screening, included-corpus, extraction, and risk-of-bias data. The writer receives only section-scoped claims/evidence and canonical work IDs. Abstract and keywords are generated after body sections. Failed sections can be retried without deleting successful sections.

Completed manuscript versions are protected by a database trigger. Manual edits clone a new version; unchanged section mappings are carried forward, while edited sections must be re-established and re-reviewed.

## Citation and export

Writers emit internal `{cite:<work_uuid>}` markers. `CitationResolver` validates canonical WorkRecord metadata, flags incomplete metadata, deduplicates used works, and renders APA 7 or Vancouver in-text citations and bibliographies. It never invents authors, dates, DOI, volume, issue, or pages.

The export service renders the same structured manuscript through Markdown, DOCX, PDF, or LaTeX. Export rows persist manuscript version, style, format, exporter version, status, and object-storage location. Bibliography entries are limited to works actually cited.

## Reviewer council and revision loop

Implemented reviewer types:

- `SCIENTIFIC`: logic, overstatement, limitations, claim/evidence alignment;
- `LITERATURE_COVERAGE`: included-corpus coverage and ignored contradictions;
- `CITATION_EVIDENCE`: sentence/claim → citation → work → evidence support;
- `METHODOLOGY`: manuscript Methods versus persisted workflow artifacts;
- `WRITING`: clarity, redundancy, tone, and terminology;
- `JOURNAL`: generic format checks or configured target-journal requirements.

Every result is a `ReviewIssue` with reviewer, severity, category, evidence, recommendation, and status. Open issues create `RevisionTask` rows. Revision clones the manuscript version, updates only the scoped section, and re-runs review. Automatic revision stops after two rounds and leaves unresolved work for author review. Humans can dismiss or accept recommendations; no reviewer mutates a manuscript directly.

## UI

The manuscript workspace adds synthesis method selection and inspection, contradiction/gap display, claim ledger, claim → evidence → study → work inspection, section navigation and textarea editing, citation inspection, review filtering/actions, version-preserving edits, and export controls. The layout is a responsive three-pane desktop workspace that collapses for tablet/mobile use without requiring Markdown knowledge.

## Scientific integrity

- Evidence and claims are separate persisted artifacts.
- Citation identity is not treated as claim support.
- Contradictions are explicit and are not flattened into consensus language.
- Methods and Results facts come from persisted project artifacts.
- No unsupported references or fabricated bibliographic metadata are generated.
- No meta-analysis or statistical pooling claim is produced before EPIC-040+.
- `READY_FOR_AUTHOR_REVIEW` is an author handoff state, not journal acceptance.

## Deferred work

The following remain intentionally out of scope and are not started: EPIC-040 Outcome Data Model, EPIC-041 Meta-analysis Eligibility, EPIC-042 Effect Size Engine, EPIC-043 Pooling Engine, EPIC-044 Heterogeneity, EPIC-045 Forest Plot, EPIC-046 Sensitivity Analysis, EPIC-047 Statistical Reviewer, and EPIC-048 Meta-analysis UI. Full CSL breadth, journal-specific submission packages, and optional ZIP packaging can be added when those workflows require them.

The repository is ready for EPIC-040–048.

# PRD v0.1 — Agentic Scientific Research & Writing SaaS

**Version:** 0.1  
**Status:** Foundation Draft  
**Working Product Name:** RanahResearch  
**Product Type:** Agentic scientific research & writing SaaS

---

# 1. Product Overview

RanahResearch adalah AI agentic scientific collaborator yang membantu user
berangkat dari ide penelitian sederhana hingga menghasilkan manuscript yang
traceable, evidence-driven, direview secara internal, dan siap untuk final
author review.

User dapat memulai dari prompt sederhana seperti:

> “Buatkan artikel tentang hasil pembelajaran dengan memanfaatkan AI.”

Sistem kemudian membantu melalui:

brainstorming
→ research formulation
→ research planning
→ literature discovery
→ screening
→ evidence extraction
→ synthesis
→ manuscript writing
→ reviewer council
→ revision
→ submission candidate.

Produk bukan sekadar AI article generator.

---

# 2. Problem Statement

Scientific writing saat ini terfragmentasi antara:
- brainstorming;
- search;
- reference manager;
- PDF reading;
- screening;
- extraction;
- statistical analysis;
- writing;
- peer review;
- journal formatting.

General-purpose LLM memiliki kelemahan:
- dapat mengarang citation;
- tidak memiliki scientific audit trail;
- tidak menjalankan systematic screening yang reproducible;
- tidak memiliki persistent evidence model;
- tidak membedakan source existence dengan claim support;
- dapat mengarang angka/metode;
- long-document coherence sulit;
- tidak memiliki internal revision loop ilmiah.

---

# 3. Core Product Principles

1. Research first, writing second.
2. Semua substantive scientific claims harus traceable ke evidence.
3. LLM digunakan untuk reasoning; computation/validation deterministic dilakukan code.
4. User/author mempertahankan final scientific authority.

---

# 4. Target Users

Primary:
- postgraduate students;
- researchers;
- lecturers;
- research assistants.

Future:
- research groups;
- labs;
- universities;
- institutions;
- think tanks.

---

# 5. Jobs To Be Done

JTBD-01 — Mengubah ide menjadi research direction.  
JTBD-02 — Menentukan research/review method.  
JTBD-03 — Menemukan literature yang relevan.  
JTBD-04 — Melakukan screening.  
JTBD-05 — Memahami dan mengekstrak evidence.  
JTBD-06 — Melakukan evidence synthesis.  
JTBD-07 — Menentukan apakah meta-analysis layak.  
JTBD-08 — Menulis manuscript.  
JTBD-09 — Melakukan internal peer review.  
JTBD-10 — Menyiapkan submission package.

---

# 6. Supported Research Modes

Initial:
- Narrative Literature Review
- Scoping Review
- Systematic Literature Review
- Systematic Review + Meta-analysis

SLR minimum workflow:
1. Research Question
2. Review Protocol
3. Eligibility Criteria
4. Database Selection
5. Search Strategy
6. Database Queries
7. Records Identified
8. Deduplication
9. Title/Abstract Screening
10. Full-text Screening
11. Included Studies
12. Data Extraction
13. Risk-of-Bias / Quality Assessment
14. Evidence Synthesis
15. PRISMA Reporting
16. Manuscript

Meta-analysis hanya dijalankan jika evidence kompatibel.

---

# 7. Future Research Modes

- Bibliometric Analysis
- Empirical Research Support

---

# 8. Core User Journey

## Phase 1 — Idea

User memasukkan rough idea.

## Phase 2 — Brainstorming / Exploration

System dapat:
- mengusulkan research direction;
- melakukan exploratory literature discovery;
- mempersempit scope;
- mencari preliminary gaps;
- menyusun candidate research questions.

User dapat memilih atau berkata “lanjut aja”.

---

# 9. Research Planning

Research Plan mencakup:
- provisional title;
- problem statement;
- objective;
- research questions;
- research method;
- research framework;
- scope;
- databases;
- timeframe;
- synthesis strategy.

User dapat:
- approve;
- modify;
- discuss;
- regenerate.

---

# 10. Framework Selection

Supported:
- PICO
- PICOS
- PCC
- SPIDER

Sistem memilih framework berdasarkan research intent.

User tidak wajib memahami singkatan framework terlebih dahulu.

---

# 11. Scientific Orchestrator

Scientific Orchestrator:
- membaca current project state;
- menentukan next action;
- memilih agent/tool;
- mengevaluasi hasil;
- menyimpan state;
- memicu gate/review/revision.

Workflow dapat loop dan kembali ke tahap sebelumnya.

---

# 12. Primary Agents

- Scientific Orchestrator
- Research Director
- Protocol Agent
- Search Strategist
- Literature Search Agent
- Screening Agent
- Evidence Extraction Agent
- Evidence Synthesis Agent
- Meta-analysis Agent / Coordinator
- Manuscript Writer
- Revision Agent

Screening output:
INCLUDE / EXCLUDE / UNCERTAIN + reason + confidence + evidence.

Writer tidak boleh menggunakan citation dari model memory.

---

# 13. Reviewer Council

General:
- Scientific Reviewer
- Literature Coverage Reviewer
- Citation/Evidence Reviewer
- Methodology Reviewer
- Writing Reviewer
- Journal Reviewer

SLR-specific:
- Protocol Reviewer
- Search Strategy Reviewer
- Screening Reviewer
- Risk-of-Bias Reviewer
- Reporting/PRISMA Reviewer

Meta-analysis:
- Statistical Reviewer
- Effect-size Reviewer
- Heterogeneity Reviewer
- Sensitivity Reviewer

---

# 14. Reviewer Revision Loop

research/write
→ review
→ issue
→ revision plan
→ research/write fix
→ re-review.

Reviewer issues adalah structured blocking tasks, bukan advisory prose saja.

---

# 15. Literature Discovery

Initial providers:
- Crossref
- OpenAlex
- Semantic Scholar

System records:
- query;
- provider;
- timestamp;
- results count;
- raw identifier;
- normalized identifier.

---

# 16. User-provided Sources

Support:
- DOI
- PDF
- BibTeX
- RIS
- CSV
- reference list

Sources can be:
- seed;
- mandatory;
- excluded.

---

# 17. Study Record

Minimum:
- internal ID;
- title;
- authors;
- year;
- DOI;
- journal;
- provider;
- abstract;
- full-text availability;
- verification;
- screening state;
- exclusion reason;
- extraction status.

Included study can include:
- population;
- sample;
- intervention/exposure;
- comparator;
- outcomes;
- design;
- country;
- findings;
- limitations.

---

# 18. Evidence Store

Evidence Store adalah structured source of truth, bukan manuscript.

---

# 19. Evidence Matrix

Filterable/sortable/exportable/correctable structured study-evidence matrix.

---

# 20. Claim Graph

Each claim links to:
- supporting evidence;
- contradictory evidence;
- uncertain evidence;
- confidence;
- manuscript location.

---

# 21. Citation Verification

Two distinct checks:
1. Source identity/existence.
2. Claim/evidence support.

Paper existence tidak berarti claim support.

---

# 22. Search Audit Trail

Store:
- databases;
- exact queries;
- timestamps;
- retrieved counts;
- pagination status;
- provider failures.

---

# 23. Deduplication

Signals:
- DOI;
- external identifiers;
- normalized title;
- author/year;
- fuzzy similarity.

All decisions auditable.

---

# 24. Screening Workspace

Fields:
- paper metadata;
- abstract/full text;
- criteria;
- AI recommendation;
- reason;
- confidence;
- human override.

---

# 25. Screening Modes

- Automatic
- Assisted
- Human Confirmation

Low-confidence cases can escalate.

---

# 26. Full-text

Retrieve/parse/index only legally available full text.

If unavailable, status must remain explicit and user may upload.

---

# 27. Data Extraction

Protocol-derived extraction schema.

Typical fields:
- characteristics;
- population;
- intervention;
- comparator;
- outcome;
- sample;
- duration;
- effects;
- uncertainty;
- limitations.

---

# 28. Risk of Bias / Quality

Assessment framework depends on study design/domain.

Reasoning/evidence/user override are persisted.

---

# 29. Meta-analysis Eligibility

Status:
- suitable;
- partially suitable;
- not suitable.

Decision considers scientific/statistical compatibility.

---

# 30. Meta-analysis Engine

Deterministic/reproducible.

Initial effect measures:
- Mean Difference
- Standardized Mean Difference
- Risk Ratio
- Odds Ratio
- Risk Difference
- Fisher’s z

---

# 31. Meta-analysis Outputs

- individual effect sizes;
- pooled estimate;
- confidence interval;
- heterogeneity;
- weights;
- model;
- forest plot.

Where appropriate:
- funnel plot;
- subgroup;
- sensitivity;
- meta-regression later.

---

# 32. Manuscript Generation

Writer consumes:
- approved plan;
- protocol;
- evidence;
- synthesis;
- claims;
- analyses.

Citations must exist in project.

---

# 33. Manuscript Workspace

Features:
- version history;
- section editing;
- citation links;
- evidence traceability;
- reviewer comments;
- revision diff.

---

# 34. Versions

Examples:
- Draft 0.1
- Draft 0.2
- Reviewer Revision 1
- Reviewer Revision 2
- Author Revision
- Submission Candidate

---

# 35. Target Journal

Fields:
- scope;
- article type;
- word limits;
- reference style;
- sections;
- abstract requirements;
- figure/table limits.

---

# 36. Submission Package

- DOCX
- PDF
- Markdown
- LaTeX
- bibliography
- BibTeX
- tables
- figures
- supplements
- audit report

Future:
- cover letter;
- highlights;
- graphical abstract;
- response letter.

---

# 37. Project State

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

Project may move backward when new evidence/issues require it.

---

# 38. Project History

Record:
- RQ change;
- protocol change;
- search;
- screening;
- manual include/exclude;
- evidence correction;
- reviewer issue;
- revision;
- issue resolution.

---

# 39. Human-in-the-loop

User can approve/modify:
- RQ;
- plan;
- protocol;
- screening;
- extraction;
- manuscript;
- analysis decisions;
- final submission.

---

# 40. Scientific Integrity

System must not:
- fabricate references;
- fabricate data;
- fabricate findings;
- pretend inaccessible full text was read;
- fake statistical outputs;
- fake PRISMA counts;
- fake SLR methods;
- hide contradictory evidence;
- misrepresent analysis.

---

# 41. Claim Language

Wording strength must be calibrated to evidence strength and design.

---

# 42. Transparency

Expose:
- provenance;
- screening rationale;
- extraction evidence;
- claim sources;
- critical agent/model runs;
- statistical method.

---

# 43. SaaS Requirements

- accounts;
- projects;
- ownership;
- future organizations;
- usage tracking;
- plans;
- billing;
- storage;
- async jobs;
- notifications;
- persistence.

---

# 44. Usage Metering

Track:
- LLM input/output tokens;
- academic searches;
- full-text processing;
- papers screened;
- extraction;
- meta-analysis runs;
- storage;
- exports.

---

# 45. Dashboard

Shows:
- project;
- review type;
- status;
- progress;
- discovered;
- screened;
- included;
- extracted;
- reviewer issues;
- manuscript state.

---

# 46. Progress UI

Examples:
- Research Question ✓
- Protocol ✓
- Search 4/4 databases
- Records 2,152
- Duplicates removed 487
- Title/abstract screening 82%
- Full-text screening 61%
- Included 72
- Extraction 43/72
- Synthesis pending

---

# 47. Conversational Interface

Chat can modify project state through structured commands.

Examples:
- change scope;
- exclude study type;
- rerun targeted search;
- resolve reviewer issue.

---

# 48. Structured Workspaces

Besides chat:
- Protocol
- Literature
- Screening
- Evidence
- Meta-analysis
- Manuscript
- Review Reports

---

# 49. Notifications

Notify on:
- search completion;
- screening completion;
- extraction completion;
- meta-analysis completion;
- manuscript/review completion;
- required human input.

---

# 50. Functional Requirements

FR-001 Create project from research idea.  
FR-002 Brainstorm/refine idea.  
FR-003 Generate research direction.  
FR-004 Select review method.  
FR-005 Select research framework.  
FR-006 Generate research plan.  
FR-007 Build protocol.  
FR-008 Generate search strategy.  
FR-009 Execute provider searches.  
FR-010 Normalize records.  
FR-011 Deduplicate.  
FR-012 Verify source identity.  
FR-013 Screen title/abstract.  
FR-014 Screen full text.  
FR-015 Store exclusion reasons.  
FR-016 Extract evidence.  
FR-017 Build evidence matrix.  
FR-018 Synthesize evidence.  
FR-019 Identify gaps/contradictions.  
FR-020 Assess meta-analysis eligibility.  
FR-021 Execute deterministic meta-analysis.  
FR-022 Generate manuscript.  
FR-023 Link manuscript claims to evidence.  
FR-024 Run Reviewer Council.  
FR-025 Execute revision loop.  
FR-026 Export manuscript/research artifacts.

---

# 51. Non-functional Requirements

Reliability  
Reproducibility  
Traceability  
Scalability  
Privacy/Security  
Cost Awareness  
Provider Independence

System should support hundreds to thousands of records per project.

---

# 52. MVP Scope

- conversational project creation;
- brainstorming/RQ/Research Director;
- Narrative Review;
- Scoping Review;
- Systematic Review;
- initial standard-effect meta-analysis;
- OpenAlex/Crossref/Semantic Scholar;
- normalization/dedup/verification;
- title/abstract screening;
- human review and exclusion reasons;
- structured extraction;
- evidence matrix;
- synthesis;
- outline/manuscript;
- citations;
- Scientific/Evidence/Citation/Method/Writing reviewers;
- reviewer issue tracking;
- automatic revision loop;
- Markdown/DOCX/PDF/bibliography export.

---

# 53. MVP Simplifications

Not initial:
- advanced journal integration;
- advanced collaboration;
- network meta-analysis;
- auto-submission;
- bibliometrics;
- empirical research;
- advanced graphical abstract.

---

# 54. Out of Scope Initial

- conducting experiments;
- fake datasets;
- replacing researcher accountability;
- acceptance guarantee;
- paywall bypass;
- automatic submission without explicit user action;
- bibliometric networks;
- network meta-analysis;
- full primary empirical research workflow.

---

# 55. Completion Criteria — General

- RQ defined;
- method defined;
- search completed;
- sources processed;
- evidence extracted;
- synthesis complete;
- manuscript complete;
- citations valid;
- zero critical citation/reviewer issues;
- export succeeds.

---

# 56. Completion Criteria — SLR

- approved protocol;
- eligibility criteria;
- search strategy;
- executed search logs;
- dedupe trace;
- screening decisions;
- exclusion reasons;
- included study list;
- extraction;
- appraisal where required;
- reporting counts consistent with DB.

---

# 57. Completion Criteria — Meta-analysis

- pooling eligibility confirmed;
- quantitative studies selected;
- inputs traceable;
- effects reproducible;
- model recorded;
- pooled estimate and uncertainty;
- heterogeneity;
- forest plot;
- zero critical statistical issues.

---

# 58. Success Metrics

- activation idea→plan;
- synthesis completion;
- author-review completion;
- evidence integrity;
- screening recall/precision;
- false exclusion rate;
- time-to-research-plan;
- time-to-manuscript;
- retention.

---

# 59. Quality Metrics

- citation validity;
- claim-evidence alignment;
- coverage;
- reviewer agreement;
- coherence;
- methodology compliance;
- hallucination rate;
- extraction accuracy;
- statistical correctness.

---

# 60. Differentiation

RanahResearch positions itself as an **Agentic Scientific Research Platform**, differentiated by:
- research-first workflow;
- persistent project state;
- evidence-centric architecture;
- dynamic orchestrator;
- reviewer council;
- revision loop;
- real SLR support;
- reproducible meta-analysis;
- auditability;
- submission-oriented output.

---

# 61. Relationship to OpenDraft

OpenDraft is used as a reference/engineering donor.

Potential adaptation:
- academic API provider code;
- DOI lookup/verification concepts;
- retry/backoff/rate-limit patterns;
- citation compilation ideas;
- document export patterns.

Core is rewritten for:
- dynamic orchestration;
- SaaS;
- SLR;
- meta-analysis;
- structured evidence;
- reviewer loops;
- multi-user persistence.

---

# 62. Product-level Domain Model

User owns ResearchProject containing:
ResearchIdea, ResearchPlan, ResearchQuestion, ReviewProtocol, SearchStrategy,
SearchRun, WorkRecord, Study, ScreeningDecision, Evidence, Outcome, Claim,
Synthesis, MetaAnalysis, Manuscript, ReviewIssue, Revision, Export.

---

# 63. High-level Workflow

USER IDEA  
→ SCIENTIFIC ORCHESTRATOR  
→ RESEARCH DIRECTOR  
→ RESEARCH PLAN  
→ PROTOCOL  
→ SEARCH STRATEGY  
→ LITERATURE DISCOVERY  
→ DEDUPLICATION  
→ SCREENING  
→ FULL TEXT  
→ EVIDENCE EXTRACTION  
→ EVIDENCE STORE  
→ SYNTHESIS / META-ANALYSIS  
→ CLAIM GRAPH  
→ MANUSCRIPT  
→ REVIEWER COUNCIL  
→ REVISION LOOP  
→ AUTHOR REVIEW  
→ SUBMISSION PACKAGE

---

# 64. Status Language

Use:
- Research in Progress
- Evidence Synthesis Complete
- Manuscript Draft
- Internal Review
- Revision Required
- Ready for Author Review
- Submission Candidate

Avoid “guaranteed publication ready”.

---

# 65. Roadmap

Phase 0 — Foundation  
Phase 1 — Research Core  
Phase 2 — Systematic Review  
Phase 3 — Meta-analysis  
Phase 4 — Submission Workflow  
Phase 5 — Bibliometric Analysis  
Phase 6 — Empirical Research

---

# 66. Open Product Decisions

- product naming;
- pricing;
- free limits;
- default model/provider;
- screening thresholds;
- initial disciplines;
- organization features;
- default autonomy;
- journal integrations;
- exact meta-analysis methods.

---

# 67. Definition of MVP Success

User can go from:
idea → RQ → plan → discovery → verified structured literature → screening →
evidence matrix → synthesis → full manuscript → internal review → automated
revision → Ready for Author Review.

Where scientifically appropriate, SLR/basic meta-analysis includes complete audit trail.

---

# 68. North Star

“Cursor/Claude Code for scientific research.”

Equivalent of a codebase:
Research Project + Literature Corpus + Evidence Store + Manuscript + Review History.

---

# 69. Final Product Statement

RanahResearch is an agentic scientific research and writing SaaS that transforms
an initial research idea into a traceable, evidence-driven manuscript through
autonomous research planning, literature discovery, systematic screening,
evidence synthesis, optional meta-analysis, scientific writing, internal peer
review, and iterative revision.

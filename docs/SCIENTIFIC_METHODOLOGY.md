# Scientific Methodology Specification v0.1

**Status:** Foundation Scientific Rules  
**Product:** RanahResearch

---

# 1. Purpose

Defines the scientific rules that govern research planning, review-method
selection, protocol development, search, screening, extraction, appraisal,
synthesis, meta-analysis, manuscript generation, and review.

---

# 2. Fundamental Principles

1. Evidence before manuscript.
2. Method description must reflect work actually performed.
3. Reproducibility.
4. Traceability.
5. No fabricated research activity.

---

# 3. Review Method Classification

Narrative Review — flexible evidence synthesis.

Scoping Review — mapping concepts/evidence/gaps.

Systematic Literature Review — reproducible focused review.

Systematic Review + Meta-analysis — systematic review with quantitative pooling
when scientifically/statistically appropriate.

---

# 4. Narrative Review

Supported for broad conceptual synthesis and thematic discussion.

Must not falsely claim:
- exhaustive search;
- PRISMA-style screening;
- systematic completeness.

---

# 5. Scoping Review

Purpose:
- evidence mapping;
- concept clarification;
- coverage analysis;
- gap identification.

PCC is a common framework.

Reporting should support PRISMA-ScR principles.

---

# 6. Systematic Review Minimum Workflow

Research Question  
→ Review Protocol  
→ Eligibility Criteria  
→ Database Selection  
→ Search Strategy  
→ Database Queries  
→ Records Identified  
→ Deduplication  
→ Title/Abstract Screening  
→ Full-text Screening  
→ Included Studies  
→ Data Extraction  
→ Risk-of-Bias/Quality Assessment  
→ Evidence Synthesis  
→ Reporting  
→ Manuscript

---

# 7. PRISMA

PRISMA is treated as a reporting framework, not as a substitute for methodology.

PRISMA flow counts must be generated from actual database/project state.

No LLM-estimated numbers.

---

# 8. Reporting Extensions

Initial standards registry:
- PRISMA 2020
- PRISMA-S
- PRISMA-ScR

---

# 9. Research Question Framework Selection

Framework is selected based on the nature of the research question.

---

# 10. PICO

Population  
Intervention  
Comparator  
Outcome

Best suited for intervention/effect questions.

---

# 11. PICOS

PICO + Study Design.

Useful when design constraints are important.

---

# 12. PCC

Population  
Concept  
Context

Common for scoping/mapping questions.

---

# 13. SPIDER

Sample  
Phenomenon of Interest  
Design  
Evaluation  
Research Type

Useful for qualitative/mixed-method experience/perception questions.

---

# 14. Framework Selection Logic

Examples:

“Does generative AI improve student outcomes?” → PICO/PICOS.

“How is AI used in higher education?” → PCC.

“What are students’ experiences using ChatGPT?” → SPIDER.

---

# 15. Review Protocol

Protocol minimum:
- background;
- objective;
- RQ;
- review type;
- framework;
- eligibility criteria;
- information sources;
- search strategy;
- screening procedure;
- extraction plan;
- appraisal plan;
- synthesis plan;
- meta-analysis plan when relevant.

---

# 16. Protocol Amendment

Material changes after protocol approval must be versioned.

Record:
- field changed;
- old/new;
- reason;
- actor;
- timestamp;
- stage.

Distinguish pre-specified from post-hoc decisions.

---

# 17. Machine-readable Eligibility

Eligibility criteria must be structured rather than only prose.

---

# 18. Eligibility Dimensions

Potential dimensions:
- population;
- intervention/exposure;
- comparator;
- outcome;
- study design;
- setting;
- publication type;
- year;
- language;
- country;
- peer-review status;
- other.

---

# 19. Information Sources

Initial:
- OpenAlex
- Crossref
- Semantic Scholar

Additional domain-specific sources can be added later.

---

# 20. Search Strategy

Search strategy should be assembled from conceptual blocks and translated to
provider-specific query syntax.

---

# 21. Search Reproducibility

Store:
- exact executed query;
- filters;
- provider;
- timestamp;
- result counts;
- pagination;
- errors.

---

# 22. Search Quality Review

Search strategy should be reviewed for:
- missing concepts;
- missing synonyms;
- excessive restriction;
- provider syntax errors;
- unnecessary date/language filters.

---

# 23. Search Expansion

May use:
- synonyms;
- controlled vocabulary;
- seed studies;
- backward citation chasing;
- forward citation chasing;
- terminology expansion.

---

# 24. Record vs Study

A publication record is not necessarily the same thing as a research study.

Multiple reports can represent one underlying study.

---

# 25. Record Deduplication vs Study Linking

Record deduplication merges duplicate bibliographic records.

Study linking groups multiple publications belonging to one underlying study.

---

# 26. Screening Stages

Initial:
- Title/Abstract
- Full Text

Optional deterministic pre-screen later.

---

# 27. Screening Decisions

INCLUDE  
EXCLUDE  
UNCERTAIN  
CONFLICT  
PENDING

---

# 28. Screening Philosophy

Title/abstract screening prioritizes recall.

Uncertain papers should not be aggressively excluded.

---

# 29. Full-text Screening

Full-text exclusion must map to explicit eligibility criterion and evidence.

High-Assurance mode supports independent duplicate screening.

---

# 30. Conflict Resolution

Independent decisions are preserved.

Conflict resolver can recommend resolution or escalate to human.

---

# 31. Exclusion Reasons

Standard reason codes should be used.

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

# 32. PRISMA Flow Counts

Derived from:
- SearchRun;
- DuplicateDecision;
- ScreeningDecision;
- included studies.

No manually authoritative PRISMA count fields.

---

# 33. Full-text Acquisition

Statuses:
- AVAILABLE_OPEN_ACCESS
- USER_UPLOADED
- LICENSED_SOURCE
- ABSTRACT_ONLY
- UNAVAILABLE
- RETRIEVAL_FAILED

No paywall circumvention.

---

# 34. Abstract-only Truthfulness

If only abstract is available, the system must not make claims requiring full-text inspection.

---

# 35. Extraction Schema

Derived from protocol.

Potential fields:
- sample;
- population;
- design;
- intervention;
- comparator;
- outcome;
- duration;
- means;
- SD;
- event count;
- effect estimate;
- uncertainty;
- findings;
- limitations.

---

# 36. Extraction Provenance

Store:
- source;
- page;
- section;
- paragraph/span;
- extracted text;
- model/run;
- confidence.

---

# 37. Numerical Extraction Validation

Numerical evidence should get stronger deterministic/independent validation.

---

# 38. Evidence Matrix

Structured, editable, auditable, exportable.

---

# 39. Quality Appraisal vs Risk of Bias

Quality of reporting and risk of bias are separate concepts.

---

# 40. Initial Risk-of-Bias Frameworks

Initial registry:
- RoB 2 for randomized trials
- ROBINS-I for non-randomized intervention studies

Additional frameworks can be discipline-configured.

---

# 41. Risk-of-Bias Provenance

Each domain judgment stores:
- tool/version;
- source evidence;
- rationale;
- reviewer;
- confidence where relevant.

---

# 42. Narrative / Qualitative Synthesis

Distinguish:
- descriptive synthesis;
- analytical interpretation.

---

# 43. Contradictory Evidence

Contradictory/null/uncertain findings must remain visible.

---

# 44. Internal Claim Strength

INSUFFICIENT  
WEAK  
MODERATE  
STRONG

---

# 45. Claim Graph

Claim links to:
- support;
- contradiction;
- uncertainty;
- confidence;
- manuscript location.

---

# 46. Meta-analysis Eligibility Criteria

Check:
- population compatibility;
- intervention/exposure;
- comparator;
- outcome;
- measurement scale;
- timepoint;
- study design;
- data availability;
- clinical/methodological heterogeneity.

---

# 47. Meta-analysis Decision States

APPROPRIATE  
APPROPRIATE_WITH_SUBGROUPS  
POSSIBLE_BUT_HIGH_RISK  
NOT_APPROPRIATE  
INSUFFICIENT_DATA

---

# 48. No Forced Pooling

A valid SLR may conclude that quantitative pooling is inappropriate.

---

# 49. Initial Effect Measures

Continuous:
- Mean Difference
- Standardized Mean Difference

Binary:
- Risk Ratio
- Odds Ratio
- Risk Difference

Correlation:
- Fisher’s z

Future:
- Hazard Ratio
- advanced effect measures.

---

# 50. Effect-size Input Provenance

Every numerical input must trace to source evidence or explicit user entry.

---

# 51. Deterministic Statistics

LLM may assist with:
- classification;
- interpretation;
- outcome mapping;
- extraction review.

LLM does not compute primary pooled statistics.

---

# 52. Common/Fixed vs Random Effects

Model selection must follow scientific assumptions, not simplistic threshold rules.

---

# 53. Heterogeneity

Initial outputs:
- Q
- I²
- τ²

Interpretation considers clinical/methodological/statistical heterogeneity together.

---

# 54. Prediction Interval

Use where appropriate and supported.

---

# 55. Forest Plot

Generated deterministically from stored analysis result.

---

# 56. Sensitivity Analysis

Possible:
- exclude high risk of bias;
- remove influential studies;
- alternate supported estimators/models;
- exclude imputed values.

---

# 57. Subgroup Analysis

Prefer pre-specified scientifically justified subgroups.

Post-hoc subgroup findings must be labeled exploratory.

---

# 58. Meta-regression

Later capability; requires sufficient studies and careful interpretation.

---

# 59. Funnel / Asymmetry

Treat funnel asymmetry cautiously. It does not automatically prove publication bias.

---

# 60. Statistical Reviewer

Validates:
- effect measure;
- extraction;
- coding;
- direction;
- model;
- heterogeneity;
- sensitivity;
- interpretation.

---

# 61. Manuscript Writer

Writer consumes structured research artifacts only.

---

# 62. Citation Rules

No citation may originate only from model training memory.

---

# 63. Claim-Evidence Validation

Verdicts:
SUPPORTED  
PARTIALLY_SUPPORTED  
CONTRADICTED  
UNCERTAIN  
UNSUPPORTED

---

# 64. Systematic Review Manuscript Sections

Typical:
- Title
- Abstract
- Introduction
- Methods
- Results
- Discussion
- Conclusion
- References
- Supplementary/Audit artifacts where needed

---

# 65. Methods Generation

Methods must be generated from actual:
- protocol;
- search logs;
- screening process;
- extraction;
- appraisal;
- analysis configuration.

No invented databases or procedures.

---

# 66. Results Generation

Results numbers derive from project state.

---

# 67. Discussion Rules

Discussion must:
- distinguish findings from interpretation;
- reflect uncertainty;
- include contradictory evidence;
- avoid causal overstatement;
- discuss limitations.

---

# 68. Limitations

Automatically consider:
- search coverage;
- database limitations;
- screening uncertainty;
- missing full text;
- extraction uncertainty;
- heterogeneity;
- RoB;
- AI assistance.

---

# 69. Reviewer Council by Method

Reviewer set adapts to Narrative/Scoping/SLR/Meta-analysis.

---

# 70. Issue Severity

CRITICAL  
MAJOR  
MINOR  
ADVISORY

---

# 71. Completion Gate

No final author-review status if:
- CRITICAL issues remain;
- mandatory methodology requirements remain unresolved.

---

# 72. Human Authority

Human override is allowed but must be logged.

---

# 73. Standard vs High-Assurance Mode

High-Assurance can require:
- dual screening;
- dual extraction;
- conflict resolution;
- manual checkpoints;
- stronger provenance.

---

# 74. Scientific Artifact Hierarchy

Plan  
Protocol  
Search Strategy  
Screening Decisions  
Evidence  
Appraisal  
Synthesis  
Claims  
Analyses  
Manuscript  
Reviews

---

# 75. Artifact Versioning

Material scientific artifacts are immutable/versioned.

---

# 76. Methodology Audit Report

Can export:
- protocol versions;
- search logs;
- screening decisions;
- exclusions;
- extraction history;
- analysis settings;
- reviewer resolution.

---

# 77. Insufficient Evidence

“Insufficient evidence” is a valid scientific outcome.

---

# 78. Scientific vs Product Metrics

Scientific quality cannot be reduced to engagement or manuscript length.

---

# 79. Standards Registry

Versioned registry:
PRISMA_2020  
PRISMA_S  
PRISMA_ScR  
COCHRANE_HANDBOOK  
JBI_SCOPING  
ROB_2  
ROBINS_I

---

# 80. Discipline Configuration

Domain profiles can alter:
- preferred databases;
- terminology;
- frameworks;
- appraisal tools.

---

# 81. Meta-analysis MVP Boundary

Initial:
- aggregate pairwise meta-analysis;
- continuous;
- binary;
- correlation;
- common/fixed and random effects;
- heterogeneity;
- forest plot;
- basic sensitivity.

Not initial:
- network meta-analysis;
- IPD;
- multilevel;
- multivariate;
- diagnostic;
- Bayesian.

---

# 82. Scoping Review Boundary

Formal risk-of-bias assessment is not mandatory by default unless objective requires it.

---

# 83. Narrative Review Boundary

Search may be flexible, but actual process must be reported honestly.

---

# 84. AI Automation Disclosure

Project records where AI was used for:
- query generation;
- screening;
- extraction;
- appraisal;
- writing/review.

---

# 85. Scientific Test Suite

Required evaluations:
- source identity;
- dedup;
- screening;
- extraction;
- claim support;
- PRISMA consistency;
- statistical calculations.

---

# 86. Screening Benchmark

Primary safety concern: false exclusion.

Eligible-study recall is critical.

---

# 87. Statistical Golden Tests

Known datasets must validate:
- effect sizes;
- SE;
- variance;
- weights;
- pooled effects;
- CI;
- Q;
- I²;
- τ².

---

# 88. Recommended Human Checkpoints

- Research Plan approval
- Protocol approval
- uncertain screening
- critical extraction uncertainty
- meta-analysis eligibility
- final author review

---

# 89. Completion by Review Type

Narrative: traceable evidence and honest search reporting.

Scoping: mapping workflow and appropriate reporting.

SLR: protocol + reproducible search + screening + extraction + appraisal + consistent reporting.

Meta-analysis: SLR completion + reproducible statistical inputs/results.

---

# 90. Guiding Principle

Scientifically incomplete but truthful is always preferred over complete-looking but fabricated.

---

# 91. Relationship to Other Specs

This methodology spec constrains:
- Technical Architecture
- Data Model
- Agent Contracts
- Implementation Roadmap

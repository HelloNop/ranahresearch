# Agent Contracts & Orchestration Specification v0.1

**Product:** RanahResearch

---

# 1. Purpose

Defines agent responsibilities, inputs, outputs, tools, permissions, triggers,
failure behavior, and quality requirements.

Agents are bounded scientific capabilities, not independent chatbots.

---

# 2. Core Principle

Orchestrator decides. Agent executes. Domain state remembers. Deterministic systems validate.

---

# 3. Agent Design Rules

Every agent has:
name
version
purpose
trigger
input_schema
output_schema
allowed_tools
forbidden_actions
acceptance_criteria
failure_behavior

No agent gets “read everything and do whatever”.

---

# 4. Agent Runtime Contract

AgentResult:
status
structured_output
warnings
confidence
artifacts_created
tool_calls
usage

---

# 5. Execution Status

SUCCESS
PARTIAL
NEEDS_HUMAN
NEEDS_MORE_EVIDENCE
INVALID_INPUT
FAILED

---

# 6. Confidence

0–1 confidence can assist routing but cannot replace validation.

---

# 7. Agent Categories

1. Orchestration
2. Research Planning
3. Literature
4. Evidence
5. Analysis
6. Writing
7. Reviewer
8. Revision

---

# 8. Scientific Orchestrator

Inputs:
project_id
project_status
method
methodology_requirements
current_artifacts
open_tasks
open_review_issues
recent_events
latest_user_instruction

Output:
next_action
target_agent
task_type
task_payload
required_artifacts
requires_human
reason
priority

Forbidden:
fabricate findings;
directly write manuscript;
invent search results;
bypass methodology;
alter evidence values.

---

# 9. Methodology Guard

Deterministic MethodologyStateValidator blocks invalid progression.

---

# 10. Research Director

Purpose:
rough idea → workable research direction.

Output:
candidate_topics
recommended_direction
problem_statement
objective
candidate_questions
recommended_review_method
recommended_framework
scope
rationale
clarifications_needed

---

# 11. Research Director Behavior

Avoid unsupported novelty claims.

Use scoped language such as preliminary evidence suggests.

---

# 12. Research Director Tools

Allowed:
Exploratory Literature Search
Project Context Retrieval
Terminology Expansion

Not:
manuscript writer
meta-analysis engine
final screening decisions.

---

# 13. Framework Selector

Input:
objective
RQ
review method
domain

Output:
framework_type
elements
rationale
confidence
missing_elements

---

# 14. Protocol Agent

Input:
approved plan
RQs
framework
method
domain

Output:
protocol
eligibility
screening strategy
extraction strategy
synthesis strategy
RoB plan
meta-analysis plan

---

# 15. Protocol Constraints

No outcome-driven criteria manipulation.
No false registration claim.
No hidden post-hoc exclusions.

---

# 16. Protocol Reviewer

Checks:
alignment
framework completeness
eligibility clarity
reproducibility
bias risk
synthesis appropriateness

---

# 17. Search Strategist

Input:
protocol
framework
eligibility
providers
seed studies
domain terms

Output:
search_concepts
synonyms
provider_queries
notes
limitations

---

# 18. Search Strategist Rules

For SLR prioritize recall.

Restrictive filters must be explained.

---

# 19. Search Reviewer

Checks:
concept/synonym coverage
over-restriction
syntax
missing terminology
date/language bias.

---

# 20. Literature Search Agent

Calls LiteratureSearchService/provider tools.

Outputs:
search_run_ids
records_retrieved
provider_errors
coverage_summary

---

# 21. Literature Search Tools

OpenAlexProvider
CrossrefProvider
SemanticScholarProvider
Citation Chasing

Future:
PubMed
Europe PMC
licensed sources.

---

# 22. Literature Search Forbidden

No invented records.
No silent provider failure.
No claim of complete search with failed pagination.
No model-memory literature source.

---

# 23. Search Completion

All mandatory queries executed, pagination completed/bounded, failures recorded, records persisted.

Partial failure = PARTIAL.

---

# 24. Metadata Resolution Agent

Used only for ambiguous provider metadata conflicts.

---

# 25. Deduplication Resolver

Handles uncertain duplicate groups conservatively.

MERGE
KEEP_SEPARATE
REVIEW_REQUIRED

---

# 26. Study Linker

Groups multiple publications into one underlying study.

Uses:
authors
samples
interventions
locations
dates
trial IDs
etc.

Low confidence → human review.

---

# 27. Screening Agent

Modes:
TITLE_ABSTRACT
FULL_TEXT

Input:
work/study
eligibility
protocol version
stage
available text

Output:
decision
reason_code
rationale
criterion_assessments
confidence
evidence_spans

---

# 28. Screening Output

Decision must map to explicit criteria.

---

# 29. Screening Rules

Title/abstract:
uncertain → INCLUDE/UNCERTAIN rather than aggressive exclude.

Full text:
requires evidence-backed criterion mapping.

---

# 30. Independent Screening

High-Assurance:
Agent A and Agent B screen independently.

---

# 31. Screening Conflict Resolver

Input:
A, B, criteria, evidence.

Output:
recommended resolution
reason
requires_human

Original decisions preserved.

---

# 32. Full-text Acquisition Agent

Finds legal OA/user/licensed sources.

No paywall bypass.

---

# 33. Evidence Extractor

Input:
study
full-text chunks
extraction schema
RQ

Output:
extracted_fields
missing_fields
uncertain_fields

Every field:
name
value
unit
source location
evidence text
confidence

---

# 34. Evidence Extraction Rule

Distinguish REPORTED vs DERIVED.

Derived values must record derivation.

---

# 35. Numerical Evidence Reviewer

Checks:
n
means
SD
SE
CI
events
percentages
arm mapping
internal consistency.

---

# 36. Evidence Reviewer

Verdict:
VERIFIED
PARTIAL
CONFLICT
UNVERIFIED

---

# 37. Risk-of-Bias Agent

Uses design-appropriate assessment framework.

Stores domain judgments + source evidence.

---

# 38. Risk-of-Bias Forbidden

No overall judgment without domain-level reasoning.

---

# 39. Evidence Synthesis Agent

Output:
themes
patterns
contradictions
uncertainties
gaps
candidate_claims

---

# 40. Synthesis Rules

Must preserve contradictory/null findings and methodological differences.

---

# 41. Gap Analysis Agent

Output gap type/description/evidence/confidence.

“No studies exist” must be scoped to actual search.

---

# 42. Claim Builder

Output:
claim_text
claim_type
strength
supporting IDs
contradicting IDs
uncertainty

---

# 43. Claim Strength

INSUFFICIENT
WEAK
MODERATE
STRONG

Association cannot be upgraded to causality without support.

---

# 44. Meta-analysis Eligibility Agent

Output:
APPROPRIATE
APPROPRIATE_WITH_SUBGROUPS
POSSIBLE_BUT_HIGH_RISK
NOT_APPROPRIATE
INSUFFICIENT_DATA

---

# 45. Meta-analysis Eligibility Rules

Consider population/intervention/comparator/outcome/scale/timepoint/design/data.

Does not compute statistics.

---

# 46. Outcome Harmonizer

Maps heterogeneous outcome labels cautiously.

Low confidence escalates.

---

# 47. Effect Size Planner

Chooses effect measure and required inputs.

Does not calculate primary numbers.

---

# 48. Statistical Engine

Not an LLM agent.

Functions:
calculate_effect_size
pool_effects
calculate_heterogeneity
run_sensitivity
run_subgroup

---

# 49. Statistical Reviewer

Checks measure, direction, mapping, model, interpretation.

Can create CRITICAL issue.

---

# 50. Manuscript Planner

Input:
method
RQs
protocol
synthesis
analysis
journal

Output:
outline
section objectives
claim allocation
table/figure plan

---

# 51. Manuscript Writer

Runs per section.

Input:
section objective
claims
supporting/contradicting evidence
analysis
citation map
style constraints
previous section summary

Output:
content
used claim IDs
used citation IDs
new interpretation statements
warnings

---

# 52. Writer Rules

No invented citations/data/methods/statistics.

No hiding contradictions.

No silent protocol changes.

---

# 53. Writer Tools

Allowed:
Claim Retrieval
Evidence Retrieval
Citation Resolver
Manuscript State Reader

Not:
Academic Search directly
Statistics directly
Protocol mutation
Screening mutation

Need more evidence → NEEDS_MORE_EVIDENCE.

---

# 54. Methods Writer

Uses actual protocol/search/screening/extraction/RoB/analysis configuration.

---

# 55. Results Writer

Uses actual counts/evidence/analysis results only.

---

# 56. Discussion Writer

Separates:
finding
interpretation
implication
speculation.

---

# 57. Abstract Writer

Runs after manuscript largely complete.

No new findings.

---

# 58. Scientific Reviewer

Checks:
RQ alignment
logic
overclaiming
conclusions
coherence.

---

# 59. Claim-Evidence Reviewer

SUPPORTED
PARTIALLY_SUPPORTED
CONTRADICTED
UNCERTAIN
UNSUPPORTED

---

# 60. Citation Reviewer

Checks:
source exists
metadata valid
citation identity
placement
actual claim relevance/support.

---

# 61. Coverage Reviewer

Can run targeted search/citation chasing.

Cannot automatically insert citations.

---

# 62. Systematic Review Reviewer

Checks:
protocol
search
screening
exclusions
extraction
RoB
reporting consistency.

---

# 63. PRISMA Reviewer

Compares reported counts with actual DB-derived counts.

---

# 64. Writing Reviewer

Checks clarity, academic tone, redundancy, flow, terminology.

Cannot silently change scientific claims.

---

# 65. Journal Reviewer

Checks journal format/requirements.

Does not predict acceptance.

---

# 66. Reviewer Independence

Reviewer should not inherit writer’s self-justification/internal reasoning.

---

# 67. Reviewer Output

overall_status
issues[]

Issue:
severity
category
location
description
evidence
suggested_action

---

# 68. Issue Severity

CRITICAL
MAJOR
MINOR
ADVISORY

---

# 69. Revision Planner

Open issues → ordered revision tasks and dependencies.

---

# 70. Revision Agent

Modifies manuscript after upstream scientific correction.

---

# 71. Critical Issue Resolution

Revision agent cannot close its own CRITICAL issue.

Reviewer/independent validator must recheck.

---

# 72. Human Decision State

HUMAN_DECISION_REQUIRED for major scientific ambiguity.

---

# 73. Tool Permission Model

Scopes:
literature.search
literature.read_metadata
fulltext.read
evidence.read
evidence.write
protocol.read
protocol.write
manuscript.read
manuscript.write
statistics.run

---

# 74. Permission Matrix

Research Director — search limited, no manuscript/statistics.

Protocol Agent — protocol write, limited search.

Search Agent — literature search only.

Screening Agent — full-text read, no evidence write.

Evidence Extractor — full-text read + evidence write.

Synthesis — evidence read.

Writer — evidence/claim read + manuscript write.

Stat Reviewer — analysis/evidence read.

Revision Agent — manuscript write with validated upstream input.

---

# 75. Context Builder

Agents get scoped contexts, not entire project dump.

---

# 76. Token Budgeting

Each contract can define context/output budgets.

Context Builder prioritizes structured evidence and relevant chunks.

---

# 77. Tool-call Limits

Tasks may define:
max_tool_calls
max_search_calls
max_tokens
max_cost.

---

# 78. Model Routing

Capability tiers:
FAST
STANDARD
HIGH_REASONING
HIGH_PRECISION_EXTRACTION

Contract specifies tier, not exact model.

---

# 79. Structured Outputs

Critical scientific outputs use strict schema validation.

---

# 80. Schema Failure

Repair → retry → fail.

Never silently accept malformed output.

---

# 81. Agent Versioning

Store:
agent version
prompt version
model
input artifact versions.

---

# 82. Prompt Architecture

System contract
+ method rules
+ task
+ scoped context
+ output schema.

No giant irrelevant prompt.

---

# 83. Agent Evals

Every major agent has benchmark.

---

# 84. Screening Primary Metric

Eligible-study recall / false exclusion risk.

---

# 85. Extraction Metrics

Field accuracy
numerical accuracy
source-span accuracy
missing-data honesty.

---

# 86. Writer Metrics

Unsupported claim rate
citation correctness
claim fidelity
coverage
coherence.

---

# 87. Reviewer Metrics

True issue detection
false alarms
critical error recall.

---

# 88. Orchestrator Metrics

Correct next action
method compliance
unnecessary calls
cost
human escalation
completion.

---

# 89. Failure Philosophy

NEEDS_MORE_EVIDENCE and NEEDS_HUMAN are valid outcomes.

---

# 90. Agent Communication

Agents communicate via:
domain state
artifacts
tasks
review issues.

Not hidden agent-to-agent chats.

---

# 91. No Hidden Agent Memory

Every run reproducible from:
AgentRun
InputArtifacts
PromptVersion
ToolResults.

---

# 92. Conversation Layer

Interprets user intent, explains status, proposes choices, emits structured commands.

Conversation is not scientific state.

---

# 93. Natural Language to Command

“Exclude papers before 2020.”
→ candidate Protocol Amendment.

---

# 94. Autonomy Modes

GUIDED
BALANCED
AUTONOMOUS

Critical ambiguity/final submission still escalates.

---

# 95. Example Agentic Workflow

Idea
→ Research Director
→ Framework
→ Protocol
→ Protocol Reviewer
→ Search Strategist
→ Search Reviewer
→ Literature Search
→ Dedupe
→ Screening
→ Full Text
→ Extraction
→ Evidence Reviewer
→ RoB
→ Synthesis
→ Meta-analysis Eligibility
→ Statistical Engine if appropriate
→ Statistical Reviewer
→ Claim Builder
→ Manuscript Planner
→ Writers
→ Reviewer Council
→ Revision
→ Re-review
→ Ready for Author Review

---

# 96. Dynamic Workflow

Synthesis can trigger targeted search and loop back through screening/extraction.

---

# 97. Agent Registry

Versioned production registry.

---

# 98. Feature Flags

Support environment/org/project/evaluation cohort rollout.

---

# 99. Agent Cost Policy

Cheap model → uncertain cases stronger model → human.

---

# 100. Confidence Escalation

Example:
FAST screening high confidence → accept.
Low confidence → high-precision.
Still uncertain → human.

---

# 101. High-Assurance Mode

May require:
dual screening
dual extraction
conflict resolution
manual checkpoints.

---

# 102. Output Provenance

Scientific artifacts record:
agent run
model
prompt
source artifact versions.

---

# 103. Scientific Completion Policy

READY_FOR_AUTHOR_REVIEW requires:
MethodologyValidator PASS
ScientificQualityGate PASS
0 CRITICAL issues
0 mandatory unresolved MAJOR issues.

---

# 104. Scientific Quality Gate

Uses:
protocol
search
screening
evidence
claims
analysis
reviews
manuscript.

Not primarily word count/citation density.

---

# 105. OpenDraft Relationship

Role mapping only:
Scout → Search
Scribe → Extraction
Signal → Synthesis
Architect → Research Director/Planner
Crafter → Writer
FactCheck → Claim-Evidence Reviewer
Referee → Scientific Reviewer

No fixed OpenDraft pipeline.

---

# 106. MVP Slice 1 Agents

Scientific Orchestrator
Research Director
Search Strategist
Literature Search Agent

Goal:
idea → plan → literature.

---

# 107. MVP Slice 2

Protocol Agent
Screening Agent
Evidence Extractor
Evidence Reviewer

Goal:
SLR research corpus.

---

# 108. MVP Slice 3

Synthesis Agent
Claim Builder
Manuscript Planner
Manuscript Writer
Scientific Reviewer
Claim-Evidence Reviewer
Revision Agent

Goal:
evidence → reviewed manuscript.

---

# 109. MVP Slice 4

RoB Agent
Meta-analysis Eligibility
Outcome Harmonizer
Effect Size Planner
Statistical Reviewer
+ deterministic Statistical Engine.

---

# 110. Agent Definition of Done

Contract
schema
tool permissions
prompt version
structured validation
tests
eval dataset
baseline eval
telemetry
failure behavior.

---

# 111. Final Agent Architecture

User
→ Conversational Interface
→ Scientific Orchestrator
→ Research Planning / Research Execution / Quality Control
→ Revision Loop
→ Ready for Author Review.

---

# 112. Final Principle

The value is not the number of agents.

The value is reliable coordination of specialized, auditable scientific capabilities.

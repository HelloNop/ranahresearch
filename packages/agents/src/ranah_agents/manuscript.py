import json
import re
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator
from ranah_domain.enums import (
    AgentRunStatus,
    ClaimType,
    ReviewerType,
    ReviewSeverity,
    SectionType,
    SynthesisMethod,
)
from ranah_domain.schemas.screening import StrictModel, Text
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.models import Message, Role
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.prompts import load_prompt
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult


class EvidenceContext(StrictModel):
    evidence_id: UUID
    study_id: UUID
    work_id: UUID | None = None
    study_type: str
    field_name: str
    value: object | None = None
    verification_status: str
    risk_of_bias: str | None = None


class SynthesisInput(StrictModel):
    method: SynthesisMethod = SynthesisMethod.NARRATIVE_SYNTHESIS
    research_question: Text
    protocol: dict[str, object] | None = None
    extraction_schema: dict[str, object]
    evidence: list[EvidenceContext] = Field(min_length=1)


class EvidenceReference(StrictModel):
    evidence_id: UUID
    relationship: Literal["SUPPORTS", "CONTRADICTS", "QUALIFIES", "CONTEXTUALIZES"]


class ThemeCandidate(StrictModel):
    label: Text
    description: Text
    evidence: list[EvidenceReference] = Field(min_length=1)
    confidence: Literal["INSUFFICIENT", "LOW", "MODERATE", "HIGH"]


class FindingCandidate(StrictModel):
    theme_index: int = Field(ge=0)
    text: Text
    evidence: list[EvidenceReference] = Field(min_length=1)
    confidence: Literal["INSUFFICIENT", "LOW", "MODERATE", "HIGH"]


class ContradictionCandidate(StrictModel):
    description: Text
    interpretation: str | None = None
    evidence: list[EvidenceReference] = Field(min_length=2)
    confidence: Literal["INSUFFICIENT", "LOW", "MODERATE", "HIGH"]


class GapCandidate(StrictModel):
    gap_type: Literal[
        "POPULATION_GAP",
        "METHOD_GAP",
        "OUTCOME_GAP",
        "GEOGRAPHIC_GAP",
        "LONGITUDINAL_GAP",
        "INCONSISTENT_EVIDENCE",
        "OTHER",
    ]
    description: Text
    supporting_observation: Text
    scope: Text
    confidence: Literal["INSUFFICIENT", "LOW", "MODERATE", "HIGH"]

    @model_validator(mode="after")
    def corpus_scoped(self) -> "GapCandidate":
        if "reviewed corpus" not in self.scope.lower():
            raise ValueError("A research gap must be scoped to the reviewed corpus")
        return self


class SynthesisOutput(StrictModel):
    themes: list[ThemeCandidate] = Field(min_length=1)
    findings: list[FindingCandidate] = Field(min_length=1)
    contradictions: list[ContradictionCandidate] = Field(default_factory=list)
    research_gaps: list[GapCandidate] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)


def validate_synthesis(data: SynthesisInput, output: SynthesisOutput) -> None:
    supplied = {row.evidence_id for row in data.evidence}
    for group in (output.themes, output.findings, output.contradictions):
        for item in group:
            cited = {link.evidence_id for link in item.evidence}
            if not cited <= supplied:
                raise LLMInvalidResponseError("Synthesis cited evidence outside its scoped input")
    if any(finding.theme_index >= len(output.themes) for finding in output.findings):
        raise LLMInvalidResponseError("A finding references a theme that does not exist")
    for contradiction in output.contradictions:
        relations = {row.relationship for row in contradiction.evidence}
        if not {"SUPPORTS", "CONTRADICTS"} <= relations:
            raise LLMInvalidResponseError(
                "A contradiction needs both supporting and opposing evidence"
            )


class ClaimBuilderInput(StrictModel):
    research_question: Text
    findings: list[dict[str, object]] = Field(min_length=1)
    evidence: list[EvidenceContext] = Field(min_length=1)


class ClaimCandidate(StrictModel):
    source_finding_id: UUID | None = None
    claim_type: ClaimType
    text: Text
    evidence: list[EvidenceReference] = Field(min_length=1)
    confidence: Literal["INSUFFICIENT", "LOW", "MODERATE", "HIGH"]


class ClaimBuilderOutput(StrictModel):
    claims: list[ClaimCandidate] = Field(min_length=1)


def validate_claims(data: ClaimBuilderInput, output: ClaimBuilderOutput) -> None:
    supplied = {row.evidence_id: row for row in data.evidence}
    for claim in output.claims:
        cited = [supplied.get(row.evidence_id) for row in claim.evidence]
        if any(row is None for row in cited):
            raise LLMInvalidResponseError("Claim cited evidence outside its scoped input")
        supporting = [
            row
            for link, row in zip(claim.evidence, cited, strict=True)
            if link.relationship == "SUPPORTS"
        ]
        if claim.claim_type == ClaimType.CAUSAL and not any(
            row and row.study_type in {"RCT", "QUASI_EXPERIMENTAL"} for row in supporting
        ):
            raise LLMInvalidResponseError("Causal language is unsupported by the supplied designs")


class ClaimReviewInput(StrictModel):
    claim: ClaimCandidate
    evidence: list[EvidenceContext]


class ClaimReviewOutput(StrictModel):
    status: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNCERTAIN", "UNSUPPORTED"]
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    contradicting_evidence_ids: list[UUID] = Field(default_factory=list)
    reason: Text
    recommended_qualification: str | None = None
    confidence: Literal["INSUFFICIENT", "LOW", "MODERATE", "HIGH"]


def validate_claim_review(data: ClaimReviewInput, output: ClaimReviewOutput) -> None:
    supplied = {row.evidence_id for row in data.evidence}
    if not set(output.supporting_evidence_ids + output.contradicting_evidence_ids) <= supplied:
        raise LLMInvalidResponseError("Claim review cited evidence outside its scoped input")
    if output.status == "SUPPORTED" and not output.supporting_evidence_ids:
        raise LLMInvalidResponseError("A supported claim requires supporting evidence")
    if (
        output.status in {"PARTIALLY_SUPPORTED", "UNSUPPORTED"}
        and not output.recommended_qualification
    ):
        raise LLMInvalidResponseError("A weak claim requires a qualification recommendation")


class PlannerInput(StrictModel):
    article_type: str
    research_question: Text
    project_artifacts: dict[str, object]
    claims: list[dict[str, object]] = Field(min_length=1)
    target_journal_constraints: dict[str, object] | None = None


class SectionPlanCandidate(StrictModel):
    section_type: SectionType
    heading: Text
    objectives: list[str] = Field(min_length=1)
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    citation_requirements: list[str] = Field(default_factory=list)
    target_words: int = Field(gt=0)


class PlannerOutput(StrictModel):
    proposed_title: Text
    sections: list[SectionPlanCandidate] = Field(min_length=1)
    word_budget: int = Field(gt=0)

    @model_validator(mode="after")
    def coherent_budget(self) -> "PlannerOutput":
        if sum(section.target_words for section in self.sections) != self.word_budget:
            raise ValueError("Section word budgets must equal the total budget")
        required = {
            SectionType.INTRODUCTION,
            SectionType.METHODS,
            SectionType.RESULTS,
            SectionType.DISCUSSION,
        }
        if not required <= {section.section_type for section in self.sections}:
            raise ValueError("The plan is missing a required body section")
        return self


class WriterInput(StrictModel):
    section_type: SectionType
    objective: Text
    claims: list[dict[str, object]]
    evidence: list[EvidenceContext]
    deterministic_facts: list[str] = Field(default_factory=list)
    allowed_work_ids: list[UUID] = Field(default_factory=list)
    previous_section_summary: str | None = None


class ClaimSpan(StrictModel):
    claim_id: UUID
    exact_text: Text


class WriterOutput(StrictModel):
    content: Text
    claim_spans: list[ClaimSpan] = Field(default_factory=list)
    cited_work_ids: list[UUID] = Field(default_factory=list)
    summary: Text
    warnings: list[str] = Field(default_factory=list)


def validate_writer(data: WriterInput, output: WriterOutput) -> None:
    allowed_claims = {UUID(str(row["id"])) for row in data.claims}
    if not {span.claim_id for span in output.claim_spans} <= allowed_claims:
        raise LLMInvalidResponseError("Section used a claim that was not supplied")
    if not set(output.cited_work_ids) <= set(data.allowed_work_ids):
        raise LLMInvalidResponseError("Section cited a work that was not supplied")
    if any(span.exact_text not in output.content for span in output.claim_spans):
        raise LLMInvalidResponseError("Claim spans must quote the generated section exactly")
    for work_id in output.cited_work_ids:
        if f"{{cite:{work_id}}}" not in output.content:
            raise LLMInvalidResponseError("Every cited work needs a canonical citation token")
    if "meta-analysis" in output.content.lower() and not any(
        "meta-analysis performed" in fact.lower() for fact in data.deterministic_facts
    ):
        raise LLMInvalidResponseError("Do not claim meta-analysis when pooling was not performed")
    prose = re.sub(r"\{cite:[0-9a-fA-F-]{36}\}", "", output.content)
    allowed = " ".join(
        [*data.deterministic_facts, *(json.dumps(row.value) for row in data.evidence)]
    )
    invented = {
        number
        for number in re.findall(r"(?<![\w-])\d+(?:\.\d+)?%?", prose)
        if number not in allowed
    }
    if invented:
        raise LLMInvalidResponseError(
            f"Section introduced numbers outside supplied facts: {sorted(invented)}"
        )


class ReviewInput(StrictModel):
    manuscript_version_id: UUID
    sections: list[dict[str, object]]
    artifacts: dict[str, object]


class ReviewIssueCandidate(StrictModel):
    section_id: UUID | None = None
    severity: ReviewSeverity
    category: Text
    description: Text
    evidence: dict[str, object] = Field(default_factory=dict)
    recommended_action: Text


class ReviewOutput(StrictModel):
    summary: str = ""
    issues: list[ReviewIssueCandidate] = Field(default_factory=list)


class RevisionInput(StrictModel):
    section: dict[str, object]
    issues: list[dict[str, object]] = Field(min_length=1)
    claims: list[dict[str, object]]
    evidence: list[EvidenceContext]
    deterministic_facts: list[str] = Field(default_factory=list)


class RevisionOutput(StrictModel):
    content: Text
    claim_spans: list[ClaimSpan] = Field(default_factory=list)
    cited_work_ids: list[UUID] = Field(default_factory=list)
    resolution_notes: list[str] = Field(min_length=1)


def validate_revision(data: RevisionInput, output: RevisionOutput) -> None:
    allowed_claims = {UUID(str(row["id"])) for row in data.claims}
    if not {span.claim_id for span in output.claim_spans} <= allowed_claims:
        raise LLMInvalidResponseError("Revision used a claim that was not supplied")
    allowed_works = {row.work_id for row in data.evidence if row.work_id}
    if not set(output.cited_work_ids) <= allowed_works:
        raise LLMInvalidResponseError("Revision cited a work that was not supplied")
    if any(span.exact_text not in output.content for span in output.claim_spans):
        raise LLMInvalidResponseError("Revision claim spans must quote the revised section")
    for work_id in output.cited_work_ids:
        if f"{{cite:{work_id}}}" not in output.content:
            raise LLMInvalidResponseError("Revision citations need canonical citation tokens")
    if "meta-analysis" in output.content.lower() and not any(
        "meta-analysis performed" in fact.lower() for fact in data.deterministic_facts
    ):
        raise LLMInvalidResponseError("Do not claim meta-analysis when pooling was not performed")


Validator = Callable[[Any, Any], None]


def _registry(
    name: str,
    purpose: str,
    input_schema: type[StrictModel],
    output_schema: type[StrictModel],
    tools: tuple[str, ...],
    validator: Validator | None = None,
) -> AgentRegistry:
    registry = AgentRegistry()
    contract = AgentContract(
        name=name,
        version="1",
        purpose=purpose,
        input_schema=input_schema,
        output_schema=output_schema,
        model_tier=ModelTier.HIGH_PRECISION_EXTRACTION,
        prompt_name=name,
        prompt_version="v1",
        allowed_tools=tools,
        forbidden_actions=("literature.search", "database.write"),
        acceptance_criteria="Return only grounded structured output using supplied identifiers",
    )

    async def execute(context: AgentContext, data: StrictModel) -> AgentResult:
        messages = [
            Message(role=Role.SYSTEM, content=load_prompt(name, "v1")),
            Message(role=Role.USER, content=data.model_dump_json()),
        ]
        result = AgentResult(status=AgentRunStatus.FAILED)

        def capture(response: Any) -> None:
            result.model = response.model
            usage = response.usage
            result.usage.input_tokens = (result.usage.input_tokens or 0) + (usage.input_tokens or 0)
            result.usage.output_tokens = (result.usage.output_tokens or 0) + (
                usage.output_tokens or 0
            )

        for _ in range(3):
            try:
                output = await context.llm.generate_structured(
                    contract.model_tier,
                    messages,
                    output_schema,
                    agent_run_id=context.agent_run_id,
                    result_hook=capture,
                )
                if validator:
                    validator(data, output)
                result.structured_output = output
                result.status = AgentRunStatus.SUCCESS
                return result
            except LLMInvalidResponseError as exc:
                messages.append(Message(role=Role.USER, content=f"Repair invalid output: {exc}"))
        result.error_code = "INVALID_AGENT_OUTPUT"
        return result

    registry.register(contract, execute)
    return registry


def synthesis_registry() -> AgentRegistry:
    return _registry(
        "synthesis_agent",
        "Synthesize validated evidence without flattening contradictions",
        SynthesisInput,
        SynthesisOutput,
        ("evidence.read", "study.read", "risk_of_bias.read", "protocol.read"),
        validate_synthesis,
    )


def claim_builder_registry() -> AgentRegistry:
    return _registry(
        "claim_builder",
        "Build evidence-linked scientific claim candidates",
        ClaimBuilderInput,
        ClaimBuilderOutput,
        ("synthesis.read", "evidence.read"),
        validate_claims,
    )


def claim_reviewer_registry() -> AgentRegistry:
    return _registry(
        "claim_evidence_reviewer",
        "Verify that claim strength does not exceed evidence",
        ClaimReviewInput,
        ClaimReviewOutput,
        ("claim.read", "evidence.read", "study.read", "risk_of_bias.read"),
        validate_claim_review,
    )


def planner_registry() -> AgentRegistry:
    return _registry(
        "manuscript_planner",
        "Map verified claims and project artifacts to a structured manuscript plan",
        PlannerInput,
        PlannerOutput,
        ("claim.read", "synthesis.read", "protocol.read", "study.read"),
    )


def writer_registry() -> AgentRegistry:
    return _registry(
        "manuscript_writer",
        "Draft one evidence-grounded manuscript section",
        WriterInput,
        WriterOutput,
        ("claim.read", "evidence.read", "study.read", "protocol.read"),
        validate_writer,
    )


def reviewer_registry(reviewer: ReviewerType) -> AgentRegistry:
    name = f"{reviewer.value.lower()}_reviewer"
    return _registry(
        name,
        f"Review a manuscript as the {reviewer.value.lower().replace('_', ' ')} reviewer",
        ReviewInput,
        ReviewOutput,
        ("manuscript.read", "claim.read", "evidence.read", "study.read", "protocol.read"),
    )


def revision_registry() -> AgentRegistry:
    return _registry(
        "revision_agent",
        "Revise one section against explicit review issues",
        RevisionInput,
        RevisionOutput,
        ("manuscript.read", "claim.read", "evidence.read", "citation.read"),
        validate_revision,
    )

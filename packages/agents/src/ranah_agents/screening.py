from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from ranah_domain.enums import AgentRunStatus, ResearchMethod
from ranah_domain.schemas.screening import (
    AGENT_FORBIDDEN_REASONS,
    REASON_DIMENSIONS,
    STAGE_ONLY_REASONS,
    Assessment,
    BoundCriterion,
    Criterion,
    ReasonCode,
    StrictModel,
    Text,
)
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.models import Message, Role
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.prompts import load_prompt
from ranah_agents.registry import AgentRegistry
from ranah_agents.research import FrameworkOutput, PlanOutput
from ranah_agents.results import AgentResult


class DiscoverySummary(StrictModel):
    canonical_records: int = Field(ge=0)
    information_sources: list[str]
    partial: bool


class ProtocolInput(StrictModel):
    plan_id: UUID
    plan_version: int
    plan: PlanOutput
    research_question: Text
    framework_id: UUID
    framework: FrameworkOutput
    discovery: DiscoverySummary
    review_method: ResearchMethod
    user_constraints: str | None = None


class ProtocolOutput(StrictModel):
    background: Text
    objective: Text
    review_type: ResearchMethod
    eligibility_criteria: Annotated[list[Criterion], Field(min_length=1, max_length=50)]
    information_sources: list[str]
    screening_strategy: Text
    extraction_strategy: Text
    synthesis_strategy: Text
    risk_of_bias_plan: Text
    meta_analysis_plan: Text
    meta_analysis_planned: bool
    assumptions: list[Text]
    uncertainties: list[Text]


class RetrievedPassage(StrictModel):
    """One passage of parsed full text, carrying where it came from."""

    page_start: int
    page_end: int
    section_path: str
    section_type: str
    text: Text


class ScreeningInput(StrictModel):
    work_id: UUID
    title: Text
    abstract: str | None
    publication_year: int | None
    language: str | None
    publication_type: str | None
    protocol_id: UUID
    protocol_version: int
    research_question: Text
    eligibility_criteria: list[BoundCriterion]
    deterministic_assessments: list[Assessment]
    stage: Literal["TITLE_ABSTRACT", "FULL_TEXT"] = "TITLE_ABSTRACT"
    passages: list[RetrievedPassage] = Field(default_factory=list)

    @model_validator(mode="after")
    def stage_inputs(self) -> "ScreeningInput":
        if self.stage == "FULL_TEXT" and not self.passages:
            raise ValueError("Full-text screening requires retrieved passages")
        if self.stage == "TITLE_ABSTRACT" and self.passages:
            raise ValueError("Title/abstract screening must not receive full text")
        return self

    def evidence_corpus(self) -> str:
        parts = [self.title, self.abstract or ""]
        parts.extend(passage.text for passage in self.passages)
        return "\n".join(parts)


class ScreeningOutput(StrictModel):
    decision: Literal["INCLUDE", "EXCLUDE", "UNCERTAIN"]
    reason_code: ReasonCode | None
    rationale: Text
    criterion_assessments: list[Assessment]
    confidence: float = Field(ge=0, le=1)
    evidence_spans: list[Text]

    @model_validator(mode="after")
    def exclusion_reason(self) -> "ScreeningOutput":
        insufficient = self.reason_code is ReasonCode.INSUFFICIENT_DATA_FOR_ELIGIBILITY
        if self.decision == "EXCLUDE":
            if not self.reason_code:
                raise ValueError("Exclusion requires a standardized reason code")
            # Exclusion for missing data rests on absent evidence, so it is the
            # one reason that cannot point at an evidenced failed criterion.
            if not insufficient and not any(
                a.result == "FAIL" and a.evidence for a in self.criterion_assessments
            ):
                raise ValueError("Exclusion requires an evidenced failed criterion")
        elif self.reason_code is not None and not (self.decision == "UNCERTAIN" and insufficient):
            raise ValueError("Only exclusions have exclusion reason codes")
        return self


def validate_screening(data: ScreeningInput, output: ScreeningOutput) -> None:
    criteria = {c.id: c for c in data.eligibility_criteria}
    ids = [a.criterion_id for a in output.criterion_assessments]
    if len(ids) != len(set(ids)) or set(ids) != set(criteria):
        raise LLMInvalidResponseError("Assess each supplied criterion exactly once")
    if output.reason_code in AGENT_FORBIDDEN_REASONS:
        raise LLMInvalidResponseError(
            "Full-text availability is a retrieval outcome recorded by the system, "
            "not a screening judgement"
        )
    if data.stage == "TITLE_ABSTRACT" and output.reason_code in STAGE_ONLY_REASONS:
        raise LLMInvalidResponseError("That reason code belongs to the full-text stage")
    text = data.evidence_corpus()
    deterministic = {a.criterion_id: a for a in data.deterministic_assessments}
    for a in output.criterion_assessments:
        known = deterministic.get(a.criterion_id)
        if known and known.result != "UNKNOWN" and a != known:
            raise LLMInvalidResponseError("Preserve trusted deterministic assessments")
        if a.evidence and a.evidence not in text and not (known and known == a):
            raise LLMInvalidResponseError("Evidence must be an exact supplied text span")
    if any(span not in text for span in output.evidence_spans):
        raise LLMInvalidResponseError("Do not invent evidence spans")
    if output.decision == "INCLUDE" and any(
        a.result == "FAIL" for a in output.criterion_assessments
    ):
        raise LLMInvalidResponseError("Resolve failed criteria before recommending inclusion")
    if output.decision == "EXCLUDE":
        if output.reason_code is ReasonCode.INSUFFICIENT_DATA_FOR_ELIGIBILITY:
            if not any(a.result == "UNKNOWN" for a in output.criterion_assessments):
                raise LLMInvalidResponseError(
                    "Insufficient-data exclusion requires at least one criterion left UNKNOWN"
                )
            return
        expected = REASON_DIMENSIONS.get(output.reason_code) if output.reason_code else None
        failures = [
            a
            for a in output.criterion_assessments
            if a.result == "FAIL"
            and a.evidence
            and (expected is None or criteria[a.criterion_id].dimension == expected)
        ]
        if not failures:
            raise LLMInvalidResponseError("Reason must map to an evidenced failed criterion")


def screening_registry() -> AgentRegistry:
    registry = AgentRegistry()
    # screening_agent v2 covers both stages; its prompt is stage-aware rather
    # than a second agent (docs/AGENT_CONTRACTS.md #27).
    schemas: list[tuple[str, str, str, type[BaseModel], type[BaseModel]]] = [
        ("protocol_agent", "1", "v1", ProtocolInput, ProtocolOutput),
        ("screening_agent", "2", "v2", ScreeningInput, ScreeningOutput),
    ]
    for name, version, prompt_version, input_schema, output_schema in schemas:
        contract = AgentContract(
            name=name,
            version=version,
            purpose=name.replace("_", " "),
            input_schema=input_schema,
            output_schema=output_schema,
            model_tier=ModelTier.STANDARD,
            prompt_name=name,
            prompt_version=prompt_version,
            allowed_tools=("protocol.read", "literature.read_metadata", "fulltext.read")
            if name == "screening_agent"
            else ("protocol.read", "literature.read_metadata"),
            forbidden_actions=(
                "protocol.write",
                "literature.search",
                "evidence.write",
                "manuscript.write",
            ),
            acceptance_criteria="Evidence-backed structured artifact with explicit uncertainty",
        )

        def executor(selected: AgentContract):  # type: ignore[no-untyped-def]
            async def execute(
                context: AgentContext, data: ProtocolInput | ScreeningInput
            ) -> AgentResult:
                messages = [
                    Message(
                        role=Role.SYSTEM,
                        content=load_prompt(selected.prompt_name, selected.prompt_version),
                    ),
                    Message(role=Role.USER, content=data.model_dump_json()),
                ]
                result = AgentResult(status=AgentRunStatus.FAILED)

                def capture(response):  # type: ignore[no-untyped-def]
                    result.model = response.model
                    result.usage.input_tokens = (result.usage.input_tokens or 0) + (
                        response.usage.input_tokens or 0
                    )
                    result.usage.output_tokens = (result.usage.output_tokens or 0) + (
                        response.usage.output_tokens or 0
                    )

                for _ in range(3):
                    try:
                        output = await context.llm.generate_structured(
                            selected.model_tier,
                            messages,
                            selected.output_schema,
                            agent_run_id=context.agent_run_id,
                            result_hook=capture,
                        )
                        if isinstance(data, ProtocolInput) and isinstance(output, ProtocolOutput):
                            if output.review_type != data.review_method or set(
                                output.information_sources
                            ) != set(data.discovery.information_sources):
                                raise LLMInvalidResponseError(
                                    "Preserve review method and actual information sources"
                                )
                        if isinstance(data, ScreeningInput) and isinstance(output, ScreeningOutput):
                            validate_screening(data, output)
                        result.structured_output = output
                        result.status = AgentRunStatus.SUCCESS
                        return result
                    except LLMInvalidResponseError as exc:
                        messages.append(
                            Message(role=Role.USER, content=f"Repair invalid output: {exc}")
                        )
                result.error_code = "INVALID_AGENT_OUTPUT"
                return result

            return execute

        registry.register(contract, executor(contract))
    return registry

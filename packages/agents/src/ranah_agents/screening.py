from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from ranah_domain.enums import AgentRunStatus, ResearchMethod
from ranah_domain.schemas.screening import (
    REASON_DIMENSIONS,
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
    stage: Literal["TITLE_ABSTRACT"] = "TITLE_ABSTRACT"


class ScreeningOutput(StrictModel):
    decision: Literal["INCLUDE", "EXCLUDE", "UNCERTAIN"]
    reason_code: ReasonCode | None
    rationale: Text
    criterion_assessments: list[Assessment]
    confidence: float = Field(ge=0, le=1)
    evidence_spans: list[Text]

    @model_validator(mode="after")
    def exclusion_reason(self) -> "ScreeningOutput":
        if self.decision == "EXCLUDE" and (
            not self.reason_code
            or not any(a.result == "FAIL" and a.evidence for a in self.criterion_assessments)
        ):
            raise ValueError("Exclusion requires a reason code and evidenced failed criterion")
        if self.decision != "EXCLUDE" and self.reason_code is not None:
            raise ValueError("Only exclusions have exclusion reason codes")
        return self


def validate_screening(data: ScreeningInput, output: ScreeningOutput) -> None:
    criteria = {c.id: c for c in data.eligibility_criteria}
    ids = [a.criterion_id for a in output.criterion_assessments]
    if len(ids) != len(set(ids)) or set(ids) != set(criteria):
        raise LLMInvalidResponseError("Assess each supplied criterion exactly once")
    text = f"{data.title}\n{data.abstract or ''}"
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
    schemas: list[tuple[str, type[BaseModel], type[BaseModel]]] = [
        ("protocol_agent", ProtocolInput, ProtocolOutput),
        ("screening_agent", ScreeningInput, ScreeningOutput),
    ]
    for name, input_schema, output_schema in schemas:
        contract = AgentContract(
            name=name,
            version="1",
            purpose=name.replace("_", " "),
            input_schema=input_schema,
            output_schema=output_schema,
            model_tier=ModelTier.STANDARD,
            prompt_name=name,
            prompt_version="v1",
            allowed_tools=("protocol.read", "literature.read_metadata"),
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
                    Message(role=Role.SYSTEM, content=load_prompt(selected.prompt_name, "v1")),
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

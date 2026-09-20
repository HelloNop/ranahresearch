"""EvidenceReviewer: independent second pass over extracted values.

The reviewer receives the structured value, the schema field and the source
passages, and never the extractor's rationale. Inheriting the extractor's
reasoning would turn verification into agreement (docs/AGENT_CONTRACTS.md #66).
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator
from ranah_domain.enums import AgentRunStatus
from ranah_domain.schemas.screening import StrictModel, Text
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.models import Message, Role
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.evidence import ExtractionPassage
from ranah_agents.prompts import load_prompt
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult

Verdict = Literal["VERIFIED", "PARTIAL", "CONFLICT", "UNVERIFIED"]


class EvidenceUnderReview(StrictModel):
    evidence_id: UUID
    field_name: str
    field_label: str
    value: Any
    unit: str | None = None
    value_type: str
    derivation: str | None = None


class EvidenceReviewInput(StrictModel):
    study_id: UUID
    study_label: str
    items: list[EvidenceUnderReview] = Field(min_length=1)
    passages: list[ExtractionPassage]


class EvidenceVerdict(StrictModel):
    evidence_id: UUID
    status: Verdict
    reason: Text
    source_check: list[Text] = Field(default_factory=list)
    corrected_value: Any = None
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def grounded(self) -> "EvidenceVerdict":
        if self.status != "UNVERIFIED" and not self.source_check:
            raise ValueError("A verdict other than UNVERIFIED must quote the passage it used")
        return self


class EvidenceReviewOutput(StrictModel):
    verdicts: list[EvidenceVerdict] = Field(min_length=1)


def validate_review(data: EvidenceReviewInput, output: EvidenceReviewOutput) -> None:
    requested = {item.evidence_id for item in data.items}
    returned = [verdict.evidence_id for verdict in output.verdicts]
    if len(returned) != len(set(returned)) or set(returned) != requested:
        raise LLMInvalidResponseError("Return exactly one verdict per supplied evidence item")
    corpus = "\n".join(passage.text for passage in data.passages)
    for verdict in output.verdicts:
        for quote in verdict.source_check:
            if quote not in corpus:
                raise LLMInvalidResponseError(
                    "Source checks must quote the supplied passages exactly"
                )


def review_registry() -> AgentRegistry:
    registry = AgentRegistry()
    contract = AgentContract(
        name="evidence_reviewer",
        version="1",
        purpose="Independently verify extracted values against their sources",
        input_schema=EvidenceReviewInput,
        output_schema=EvidenceReviewOutput,
        model_tier=ModelTier.HIGH_PRECISION_EXTRACTION,
        prompt_name="evidence_reviewer",
        prompt_version="v1",
        allowed_tools=("fulltext.read", "evidence.read"),
        forbidden_actions=(
            "evidence.write",
            "literature.search",
            "protocol.write",
            "manuscript.write",
        ),
        acceptance_criteria="Quoted, independent verdict per evidence item",
    )

    async def execute(context: AgentContext, data: EvidenceReviewInput) -> AgentResult:
        messages = [
            Message(role=Role.SYSTEM, content=load_prompt("evidence_reviewer", "v1")),
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
                    contract.model_tier,
                    messages,
                    EvidenceReviewOutput,
                    agent_run_id=context.agent_run_id,
                    result_hook=capture,
                )
                assert isinstance(output, EvidenceReviewOutput)
                validate_review(data, output)
                result.structured_output = output
                result.status = AgentRunStatus.SUCCESS
                return result
            except LLMInvalidResponseError as exc:
                messages.append(Message(role=Role.USER, content=f"Repair invalid output: {exc}"))
        result.error_code = "INVALID_AGENT_OUTPUT"
        return result

    registry.register(contract, execute)
    return registry

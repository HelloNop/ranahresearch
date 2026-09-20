"""EvidenceExtractor: structured, source-grounded extraction for one study.

The validator is the enforcement point for the rules the prompt states: every
value quotes supplied text, derived values carry their arithmetic, and a field
the passages do not report stays MISSING rather than becoming a number.
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator
from ranah_domain.enums import AgentRunStatus, EvidenceValueType
from ranah_domain.schemas.screening import StrictModel, Text
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.models import Message, Role
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.prompts import load_prompt
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult


class ExtractionPassage(StrictModel):
    passage_id: int
    work_id: UUID
    parsed_document_id: UUID | None = None
    chunk_id: UUID | None = None
    page_start: int
    page_end: int
    section_path: str
    section_type: str
    text: Text


class ExtractionField(StrictModel):
    name: str
    label: str
    kind: Literal["TEXT", "NUMBER", "INTEGER", "CATEGORICAL", "LIST"]
    evidence_type: str
    unit: str | None = None
    description: str = ""


class ExtractionInput(StrictModel):
    study_id: UUID
    study_label: str
    research_question: Text
    fields: list[ExtractionField]
    passages: list[ExtractionPassage]


class SourceLocation(StrictModel):
    passage_id: int
    page: int
    quote: Text


class ExtractedField(StrictModel):
    field_name: str
    value: Any
    unit: str | None = None
    value_type: Literal["REPORTED", "DERIVED"]
    derivation: str | None = None
    confidence: float = Field(ge=0, le=1)
    source_locations: list[SourceLocation] = Field(min_length=1)

    @model_validator(mode="after")
    def derived_shows_its_work(self) -> "ExtractedField":
        if self.value_type == "DERIVED" and not (self.derivation or "").strip():
            raise ValueError("A derived value must record its derivation")
        if self.value is None:
            raise ValueError("An extracted field needs a value; report absence as missing")
        return self


class MissingField(StrictModel):
    field_name: str
    reason: Text


class UncertainField(StrictModel):
    field_name: str
    reason: Text
    candidate_value: Any = None
    source_locations: list[SourceLocation] = Field(default_factory=list)


class ExtractionOutput(StrictModel):
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    missing_fields: list[MissingField] = Field(default_factory=list)
    uncertain_fields: list[UncertainField] = Field(default_factory=list)

    @model_validator(mode="after")
    def one_verdict_per_field(self) -> "ExtractionOutput":
        names = (
            [f.field_name for f in self.extracted_fields]
            + [f.field_name for f in self.missing_fields]
            + [f.field_name for f in self.uncertain_fields]
        )
        if len(names) != len(set(names)):
            raise ValueError("Each field may appear in only one of the three lists")
        return self


def validate_extraction(data: ExtractionInput, output: ExtractionOutput) -> None:
    requested = {field.name: field for field in data.fields}
    passages = {passage.passage_id: passage for passage in data.passages}

    reported = (
        [f.field_name for f in output.extracted_fields]
        + [f.field_name for f in output.missing_fields]
        + [f.field_name for f in output.uncertain_fields]
    )
    unknown = set(reported) - set(requested)
    if unknown:
        raise LLMInvalidResponseError(f"Unrequested fields: {sorted(unknown)}")
    if set(reported) != set(requested):
        raise LLMInvalidResponseError("Account for every requested field exactly once")

    for field in output.extracted_fields:
        spec = requested[field.field_name]
        _check_locations(field.source_locations, passages, field.field_name)
        _check_kind(spec.kind, field.value, field.field_name)
        if field.value_type == "DERIVED" and len(field.source_locations) < 1:
            raise LLMInvalidResponseError("A derived value must cite its input passages")

    for uncertain in output.uncertain_fields:
        _check_locations(
            uncertain.source_locations, passages, uncertain.field_name, allow_empty=True
        )


def _check_locations(
    locations: list[SourceLocation],
    passages: dict[int, ExtractionPassage],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> None:
    if not locations and not allow_empty:
        raise LLMInvalidResponseError(f"{field_name} needs a source location")
    for location in locations:
        passage = passages.get(location.passage_id)
        if passage is None:
            raise LLMInvalidResponseError(f"{field_name} cites a passage that was not supplied")
        if location.quote not in passage.text:
            raise LLMInvalidResponseError(
                f"{field_name} quotes text that does not appear in passage {location.passage_id}"
            )
        if not passage.page_start <= location.page <= passage.page_end:
            raise LLMInvalidResponseError(
                f"{field_name} cites page {location.page}, outside the quoted passage"
            )


def _check_kind(kind: str, value: Any, field_name: str) -> None:
    if kind in ("NUMBER", "INTEGER"):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise LLMInvalidResponseError(f"{field_name} must be a plain number")
        if kind == "INTEGER" and float(value) != int(value):
            raise LLMInvalidResponseError(f"{field_name} must be a whole number")
    elif kind == "LIST":
        if not isinstance(value, list) or not value:
            raise LLMInvalidResponseError(f"{field_name} must be a non-empty list")
    elif not isinstance(value, str) or not value.strip():
        raise LLMInvalidResponseError(f"{field_name} must be non-empty text")


VALUE_TYPES = {
    "REPORTED": EvidenceValueType.REPORTED,
    "DERIVED": EvidenceValueType.DERIVED,
}


def extraction_registry() -> AgentRegistry:
    registry = AgentRegistry()
    contract = AgentContract(
        name="evidence_extractor",
        version="1",
        purpose="Extract schema fields for one study from its full-text passages",
        input_schema=ExtractionInput,
        output_schema=ExtractionOutput,
        model_tier=ModelTier.HIGH_PRECISION_EXTRACTION,
        prompt_name="evidence_extractor",
        prompt_version="v1",
        allowed_tools=("fulltext.read", "protocol.read"),
        forbidden_actions=(
            "literature.search",
            "protocol.write",
            "manuscript.write",
            "statistics.run",
        ),
        acceptance_criteria="Every value quoted from source; absence reported as missing",
    )

    async def execute(context: AgentContext, data: ExtractionInput) -> AgentResult:
        messages = [
            Message(role=Role.SYSTEM, content=load_prompt("evidence_extractor", "v1")),
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
                    ExtractionOutput,
                    agent_run_id=context.agent_run_id,
                    result_hook=capture,
                )
                assert isinstance(output, ExtractionOutput)
                validate_extraction(data, output)
                result.structured_output = output
                result.status = AgentRunStatus.SUCCESS
                return result
            except LLMInvalidResponseError as exc:
                messages.append(Message(role=Role.USER, content=f"Repair invalid output: {exc}"))
        result.error_code = "INVALID_AGENT_OUTPUT"
        return result

    registry.register(contract, execute)
    return registry

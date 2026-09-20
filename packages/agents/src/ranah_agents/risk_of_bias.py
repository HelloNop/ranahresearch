"""Tentative, source-quoted appraisal for a design-appropriate tool."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from ranah_domain.enums import AgentRunStatus, StudyType
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

TOOLS: dict[str, tuple[str, ...]] = {
    "ROB_2": (
        "randomization",
        "deviations",
        "missing_data",
        "outcome_measurement",
        "reported_result",
    ),
    "ROBINS_I": (
        "confounding",
        "participant_selection",
        "intervention_classification",
        "deviations",
        "missing_data",
        "outcome_measurement",
        "reported_result",
    ),
}
TOOL_VERSION = "foundation-1"


def select_tool(study_type: StudyType) -> Literal["ROB_2", "ROBINS_I"] | None:
    if study_type == StudyType.RCT:
        return "ROB_2"
    if study_type == StudyType.QUASI_EXPERIMENTAL:
        return "ROBINS_I"
    return None


class RiskInput(StrictModel):
    study_id: UUID
    study_label: str
    study_type: StudyType
    tool: Literal["ROB_2", "ROBINS_I"]
    tool_version: str = TOOL_VERSION
    domains: list[str]
    passages: list[ExtractionPassage] = Field(min_length=1)


class DomainJudgement(StrictModel):
    domain_code: str
    judgement: Literal["LOW_RISK", "SOME_CONCERNS", "HIGH_RISK", "UNASSESSED"]
    rationale: Text
    supporting_evidence: str = ""
    passage_id: int | None = None

    @model_validator(mode="after")
    def grounded(self) -> "DomainJudgement":
        if self.judgement != "UNASSESSED" and (
            not self.supporting_evidence or self.passage_id is None
        ):
            raise ValueError("A domain judgement needs quoted source evidence")
        return self


class RiskOutput(StrictModel):
    domain_assessments: list[DomainJudgement] = Field(min_length=1)
    overall_judgement: Literal["LOW_RISK", "SOME_CONCERNS", "HIGH_RISK", "NOT_ASSESSED"]
    uncertainties: list[str] = Field(default_factory=list)
    requires_human: bool = True

    @model_validator(mode="after")
    def coherent(self) -> "RiskOutput":
        if (
            any(d.judgement == "UNASSESSED" for d in self.domain_assessments)
            and self.overall_judgement != "NOT_ASSESSED"
        ):
            raise ValueError("Unassessed domains prevent an overall risk judgement")
        return self


def validate_risk(data: RiskInput, output: RiskOutput) -> None:
    codes = [domain.domain_code for domain in output.domain_assessments]
    if len(codes) != len(set(codes)) or set(codes) != set(data.domains):
        raise LLMInvalidResponseError("Return one judgement for every supplied domain")
    passages = {passage.passage_id: passage for passage in data.passages}
    for domain in output.domain_assessments:
        if domain.judgement == "UNASSESSED":
            continue
        passage = passages.get(domain.passage_id or -1)
        if passage is None or domain.supporting_evidence not in passage.text:
            raise LLMInvalidResponseError("Domain evidence must quote its cited passage exactly")


def risk_registry() -> AgentRegistry:
    registry = AgentRegistry()
    contract = AgentContract(
        name="risk_of_bias_agent",
        version="1",
        purpose="Propose source-grounded risk-of-bias domain judgements for human review",
        input_schema=RiskInput,
        output_schema=RiskOutput,
        model_tier=ModelTier.HIGH_PRECISION_EXTRACTION,
        prompt_name="risk_of_bias_agent",
        prompt_version="v1",
        allowed_tools=("fulltext.read", "study.read"),
        forbidden_actions=("risk_of_bias.write", "evidence.write", "manuscript.write"),
        acceptance_criteria="One source-grounded judgement per applicable domain",
    )

    async def execute(context: AgentContext, data: RiskInput) -> AgentResult:
        messages = [
            Message(role=Role.SYSTEM, content=load_prompt("risk_of_bias_agent", "v1")),
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
                    RiskOutput,
                    agent_run_id=context.agent_run_id,
                    result_hook=capture,
                )
                assert isinstance(output, RiskOutput)
                validate_risk(data, output)
                result.structured_output = output
                result.status = (
                    AgentRunStatus.NEEDS_HUMAN if output.requires_human else AgentRunStatus.SUCCESS
                )
                return result
            except LLMInvalidResponseError as exc:
                messages.append(Message(role=Role.USER, content=f"Repair invalid output: {exc}"))
        result.error_code = "INVALID_AGENT_OUTPUT"
        return result

    registry.register(contract, execute)
    return registry

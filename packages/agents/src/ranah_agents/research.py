import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from ranah_domain.enums import AgentRunStatus, ResearchFrameworkType, ResearchMethod
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.models import Message, Role, StructuredGenerateResult, Usage
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.prompts import load_prompt
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult

Text = Annotated[str, Field(min_length=1, max_length=12000)]
Provider = Literal["crossref", "openalex", "semantic_scholar"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DirectorInput(StrictModel):
    project_id: UUID
    raw_idea: Text
    existing_project_title: str
    user_preferences: str | None = None
    exploratory_literature_summary: str | None = None


class PlanOutput(StrictModel):
    provisional_title: Annotated[str, Field(min_length=1, max_length=500)]
    problem_statement: Text
    research_objective: Text
    candidate_research_questions: Annotated[list[Text], Field(min_length=1, max_length=10)]
    recommended_research_question: Text
    recommended_review_method: ResearchMethod
    recommended_framework: ResearchFrameworkType
    scope: Text
    key_concepts: Annotated[list[Text], Field(min_length=1, max_length=12)]
    assumptions: list[Text]
    uncertainties: list[Text]
    rationale: Text


class FrameworkInput(StrictModel):
    research_objective: Text
    recommended_research_question: Text
    review_method: ResearchMethod
    key_concepts: list[Text]
    domain_context: Text


class FrameworkElement(StrictModel):
    name: Text
    values: list[Text]


class FrameworkOutput(StrictModel):
    framework_type: ResearchFrameworkType
    elements: Annotated[list[FrameworkElement], Field(min_length=1)]
    missing_elements: list[Text]
    rationale: Text
    confidence: Annotated[float, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def required_elements(self) -> "FrameworkOutput":
        required = {
            "PICO": {"population", "intervention", "comparator", "outcomes"},
            "PICOS": {"population", "intervention", "comparator", "outcomes", "study_design"},
            "PCC": {"population", "concept", "context"},
            "SPIDER": {"sample", "phenomenon_of_interest", "design", "evaluation", "research_type"},
        }.get(self.framework_type, set())
        names = [element.name for element in self.elements]
        present = {element.name for element in self.elements if element.values}
        if len(names) != len(set(names)) or not required <= present | set(self.missing_elements):
            raise ValueError("Framework must identify each required element or declare it missing")
        return self


class SearchFilters(StrictModel):
    year_from: Annotated[int, Field(ge=1500, le=2100)] | None = None
    year_to: Annotated[int, Field(ge=1500, le=2100)] | None = None

    @model_validator(mode="after")
    def ordered_years(self) -> "SearchFilters":
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from must not exceed year_to")
        return self


class StrategyInput(StrictModel):
    plan: PlanOutput
    framework: FrameworkOutput
    target_providers: list[Provider]
    filters: SearchFilters


class SearchConcept(StrictModel):
    label: Text
    terms: Annotated[list[Text], Field(min_length=1, max_length=20)]


class ProviderQuery(StrictModel):
    provider: Provider
    query_text: Annotated[str, Field(min_length=1, max_length=500)]
    rationale: Text

    @model_validator(mode="after")
    def plain_query(self) -> "ProviderQuery":
        if re.search(r"\b(?:AND|OR|NOT)\b|[():*]", self.query_text):
            raise ValueError("Discovery queries must use plain terms, no Boolean or field syntax")
        return self


class StrategyOutput(StrictModel):
    concepts: Annotated[list[SearchConcept], Field(min_length=1, max_length=12)]
    provider_queries: Annotated[list[ProviderQuery], Field(min_length=3, max_length=3)]
    filters: SearchFilters
    rationale: Text
    known_limitations: list[Text]

    @model_validator(mode="after")
    def provider_coverage(self) -> "StrategyOutput":
        if {query.provider for query in self.provider_queries} != {
            "crossref",
            "openalex",
            "semantic_scholar",
        }:
            raise ValueError("Exactly one query for each discovery provider is required")
        return self


AGENT_SCHEMAS: list[tuple[str, str, type[BaseModel], type[BaseModel]]] = [
    ("research_director", "Idea to proposed research plan", DirectorInput, PlanOutput),
    ("framework_selector", "Structure a research question", FrameworkInput, FrameworkOutput),
    ("search_strategist", "Approved plan to discovery queries", StrategyInput, StrategyOutput),
]

CONTRACTS = [
    AgentContract(
        name=name,
        version="1",
        purpose=purpose,
        input_schema=input_schema,
        output_schema=output_schema,
        model_tier=ModelTier.STANDARD,
        prompt_name=name,
        prompt_version="v1",
        forbidden_actions=("provider_http", "project_mutation", "unsupported_novelty_claims"),
        acceptance_criteria="Validated provisional artifact; evidence limitations explicit.",
    )
    for name, purpose, input_schema, output_schema in AGENT_SCHEMAS
]


def research_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for contract in CONTRACTS:

        def executor_for(selected: AgentContract):  # type: ignore[no-untyped-def]
            async def execute(context: AgentContext, data: BaseModel) -> AgentResult:
                usage = Usage(input_tokens=0, output_tokens=0)
                result = AgentResult(status=AgentRunStatus.FAILED, usage=usage)

                def capture(response: StructuredGenerateResult) -> None:
                    result.model = response.model
                    usage.input_tokens = (usage.input_tokens or 0) + (
                        response.usage.input_tokens or 0
                    )
                    usage.output_tokens = (usage.output_tokens or 0) + (
                        response.usage.output_tokens or 0
                    )
                    if response.usage.estimated_cost is not None:
                        usage.estimated_cost = (
                            usage.estimated_cost or 0
                        ) + response.usage.estimated_cost

                messages = [
                    Message(role=Role.SYSTEM, content=load_prompt(selected.prompt_name, "v1")),
                    Message(role=Role.USER, content=data.model_dump_json()),
                ]
                for _ in range(3):
                    try:
                        output = await context.llm.generate_structured(
                            selected.model_tier,
                            messages,
                            selected.output_schema,
                            agent_run_id=context.agent_run_id,
                            result_hook=capture,
                        )
                        if isinstance(output, StrategyOutput) and isinstance(data, StrategyInput):
                            if output.filters != data.filters:
                                raise LLMInvalidResponseError("Preserve user filters exactly")
                        result.structured_output = output
                        result.status = AgentRunStatus.SUCCESS
                        return result
                    except LLMInvalidResponseError as exc:
                        messages.append(
                            Message(role=Role.USER, content=f"Repair the output schema: {exc}")
                        )
                result.error_code = "INVALID_AGENT_OUTPUT"
                return result

            return execute

        registry.register(contract, executor_for(contract))
    return registry

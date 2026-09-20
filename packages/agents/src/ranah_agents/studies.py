"""StudyLinker: conservative resolution of ambiguous study-link candidates.

Permissions are read-only. The agent returns a judgement; persisting a link is
the service's job, so no agent ever mutates study state directly
(docs/AGENT_CONTRACTS.md #26, #74).
"""

from uuid import UUID

from pydantic import Field, model_validator
from ranah_domain.enums import AgentRunStatus, StudyWorkRelationship
from ranah_domain.schemas.screening import StrictModel, Text
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.models import Message, Role
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.prompts import load_prompt
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult


class LinkCandidate(StrictModel):
    work_id: UUID
    title: Text
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    publication_type: str | None = None
    registration_ids: list[str] = Field(default_factory=list)
    full_text_excerpts: list[str] = Field(default_factory=list)


class StudyLinkInput(StrictModel):
    project_id: UUID
    research_question: Text
    left: LinkCandidate
    right: LinkCandidate
    deterministic_signals: dict[str, object] = Field(default_factory=dict)


class StudyLinkOutput(StrictModel):
    same_study: bool
    relationship_type: StudyWorkRelationship | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: Text
    evidence: list[Text] = Field(default_factory=list)
    requires_human: bool = False

    @model_validator(mode="after")
    def coherent(self) -> "StudyLinkOutput":
        if self.same_study and self.relationship_type is None:
            raise ValueError("A linked report needs a relationship type")
        if not self.same_study and self.relationship_type is not None:
            raise ValueError("Only linked reports carry a relationship type")
        if self.same_study and not self.evidence:
            raise ValueError("Linking two publications requires quoted evidence")
        return self


def validate_link(data: StudyLinkInput, output: StudyLinkOutput) -> None:
    """Evidence must be quoted from the supplied text, and a link that rests on
    nothing but authorship is escalated rather than asserted."""
    corpus = "\n".join(
        part
        for candidate in (data.left, data.right)
        for part in [
            candidate.title,
            candidate.abstract or "",
            *candidate.full_text_excerpts,
            *candidate.registration_ids,
        ]
    )
    for span in output.evidence:
        if span not in corpus:
            raise LLMInvalidResponseError("Evidence must be an exact span from the supplied text")

    shared_registration = data.deterministic_signals.get("registration_id")
    if output.same_study and not shared_registration and not output.requires_human:
        supporting = [
            span
            for span in output.evidence
            if any(character.isdigit() for character in span) or "same" in span.lower()
        ]
        if not supporting:
            raise LLMInvalidResponseError(
                "Without a shared registration, a link needs concrete study-identity evidence "
                "or requires_human"
            )


def study_registry() -> AgentRegistry:
    registry = AgentRegistry()
    contract = AgentContract(
        name="study_linker",
        version="1",
        purpose="Decide whether two publications report one underlying study",
        input_schema=StudyLinkInput,
        output_schema=StudyLinkOutput,
        model_tier=ModelTier.STANDARD,
        prompt_name="study_linker",
        prompt_version="v1",
        allowed_tools=("literature.read_metadata", "fulltext.read"),
        forbidden_actions=(
            "literature.search",
            "evidence.write",
            "protocol.write",
            "manuscript.write",
        ),
        acceptance_criteria="Conservative, evidence-quoted link judgement that escalates doubt",
    )

    async def execute(context: AgentContext, data: StudyLinkInput) -> AgentResult:
        messages = [
            Message(role=Role.SYSTEM, content=load_prompt("study_linker", "v1")),
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
                    StudyLinkOutput,
                    agent_run_id=context.agent_run_id,
                    result_hook=capture,
                )
                assert isinstance(output, StudyLinkOutput)
                validate_link(data, output)
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

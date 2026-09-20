"""Reference agent proving the runtime end-to-end. Not a real research capability."""

from pydantic import BaseModel
from ranah_domain.enums import AgentRunStatus
from ranah_llm.models import Message, Role
from ranah_llm.routing import ModelTier

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.results import AgentResult


class SampleAgentInput(BaseModel):
    question: str


class SampleAgentOutput(BaseModel):
    answer: str
    confidence: float


CONTRACT = AgentContract(
    name="sample_agent",
    version="v1",
    purpose="Proves the agent runtime (contract, context, LLM call, persistence) end-to-end.",
    input_schema=SampleAgentInput,
    output_schema=SampleAgentOutput,
    model_tier=ModelTier.FAST,
    prompt_name="sample_agent",
    prompt_version="v1",
    allowed_tools=(),
    forbidden_actions=("manuscript.write", "statistics.run"),
    acceptance_criteria="Returns a structured SampleAgentOutput for any question.",
)


async def execute(context: AgentContext, data: SampleAgentInput) -> AgentResult:
    output = await context.llm.generate_structured(
        CONTRACT.model_tier,
        [
            Message(role=Role.SYSTEM, content="Answer briefly and rate your own confidence."),
            Message(role=Role.USER, content=data.question),
        ],
        SampleAgentOutput,
        agent_run_id=context.agent_run_id,
    )
    return AgentResult(
        status=AgentRunStatus.SUCCESS, structured_output=output, confidence=output.confidence
    )

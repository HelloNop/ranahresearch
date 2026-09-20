"""Agents get scoped context, not an entire project dump (docs/AGENT_CONTRACTS.md #75)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ranah_llm.gateway import LLMGateway

from ranah_agents.contracts import AgentContract
from ranah_agents.tools import ScopedToolRegistry, ToolRegistry

ExtraLoader = Callable[[str], Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class AgentTask:
    task_type: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class AgentContext:
    project_id: str
    agent_run_id: str
    tools: ScopedToolRegistry
    llm: LLMGateway
    extra: dict[str, object] = field(default_factory=dict)


class ContextBuilder:
    """Assembles the bounded context an agent run actually needs."""

    def __init__(self, tool_registry: ToolRegistry, llm_gateway: LLMGateway) -> None:
        self._tools = tool_registry
        self._llm = llm_gateway

    async def build(
        self,
        contract: AgentContract,
        *,
        project_id: str,
        agent_run_id: str,
        loaders: tuple[ExtraLoader, ...] = (),
    ) -> AgentContext:
        extra: dict[str, object] = {}
        for loader in loaders:
            extra.update(await loader(project_id))
        return AgentContext(
            project_id=project_id,
            agent_run_id=agent_run_id,
            tools=self._tools.scoped_to(contract.allowed_tools),
            llm=self._llm,
            extra=extra,
        )

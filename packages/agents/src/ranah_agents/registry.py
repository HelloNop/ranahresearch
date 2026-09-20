"""Versioned production agent registry (docs/AGENT_CONTRACTS.md #97)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ranah_agents.context import AgentContext
from ranah_agents.contracts import AgentContract
from ranah_agents.results import AgentResult

# The second parameter is really "an instance of this contract's input_schema", which
# varies per agent; Any here is honest about that instead of fighting Callable variance.
AgentExecutor = Callable[[AgentContext, Any], Awaitable[AgentResult]]


@dataclass(frozen=True, slots=True)
class RegisteredAgent:
    contract: AgentContract
    executor: AgentExecutor


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], RegisteredAgent] = {}

    def register(self, contract: AgentContract, executor: AgentExecutor) -> None:
        key = (contract.name, contract.version)
        if key in self._agents:
            raise ValueError(f"agent {contract.name} v{contract.version} is already registered")
        self._agents[key] = RegisteredAgent(contract=contract, executor=executor)

    def get(self, name: str, version: str) -> RegisteredAgent:
        try:
            return self._agents[(name, version)]
        except KeyError:
            raise KeyError(f"no agent registered as {name} v{version}") from None

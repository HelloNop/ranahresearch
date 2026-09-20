"""AgentResult: what every agent execution returns, regardless of what it did internally."""

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel
from ranah_domain.enums import AgentRunStatus
from ranah_llm.models import ModelInfo, Usage


@dataclass(slots=True)
class AgentResult:
    status: AgentRunStatus
    agent_run_id: UUID | None = None
    model: ModelInfo | None = None
    structured_output: BaseModel | None = None
    warnings: list[str] = field(default_factory=list)
    confidence: float | None = None
    artifacts_created: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    error_code: str | None = None

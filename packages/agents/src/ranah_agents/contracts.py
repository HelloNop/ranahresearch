"""Every agent declares a contract. No agent gets 'read everything and do whatever'."""

from dataclasses import dataclass, field

from pydantic import BaseModel
from ranah_llm.routing import ModelTier


@dataclass(frozen=True, slots=True)
class AgentContract:
    name: str
    version: str
    purpose: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    model_tier: ModelTier
    prompt_name: str
    prompt_version: str
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    forbidden_actions: tuple[str, ...] = field(default_factory=tuple)
    acceptance_criteria: str = ""
    failure_behavior: str = "Return INVALID_INPUT/FAILED with error_code; never fabricate output."

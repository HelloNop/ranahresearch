"""Provider-neutral request/response shapes. Business logic imports these, never an SDK type."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: Role
    content: str


class Usage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None


class ModelInfo(BaseModel):
    provider: str
    model: str


class GenerateRequest(BaseModel):
    messages: list[Message]
    model: str
    temperature: float = 0.2
    max_output_tokens: int | None = None
    # Correlates this call back to an AgentRun for tracing/usage attribution.
    agent_run_id: str | None = None


class GenerateResult(BaseModel):
    text: str
    model: ModelInfo
    usage: Usage
    finish_reason: Literal["stop", "length", "error"] = "stop"


class StructuredGenerateRequest(BaseModel):
    messages: list[Message]
    model: str
    response_schema: dict[str, Any]
    schema_name: str = "response"
    temperature: float = 0.2
    agent_run_id: str | None = None


class StructuredGenerateResult(BaseModel):
    data: dict[str, Any]
    model: ModelInfo
    usage: Usage


class ToolDefinition(BaseModel):
    """Reserved for EPIC-007+ tool-calling agents; not used by the sample agent yet."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


class EmbedRequest(BaseModel):
    """Reserved for future retrieval work (pgvector); no provider implements it yet."""

    texts: list[str]
    model: str


class EmbedResult(BaseModel):
    vectors: list[list[float]]
    model: ModelInfo
    usage: Usage

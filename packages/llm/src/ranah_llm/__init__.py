"""Provider-neutral LLM layer. All model calls go through LLMGateway."""

from ranah_llm.errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import GenerateResult, Message, Role, StructuredGenerateResult, Usage
from ranah_llm.routing import DEFAULT_OPENAI_ROUTES, ModelRouter, ModelTier

__all__ = [
    "DEFAULT_OPENAI_ROUTES",
    "GenerateResult",
    "LLMAuthError",
    "LLMError",
    "LLMGateway",
    "LLMInvalidResponseError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "Message",
    "ModelRouter",
    "ModelTier",
    "Role",
    "StructuredGenerateResult",
    "Usage",
]

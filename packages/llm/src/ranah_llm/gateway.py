"""The single entry point for all model calls. Business logic depends on this,
never on a concrete provider or SDK (see docs/TECHNICAL_ARCHITECTURE.md #19-20).
"""

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ranah_llm.errors import LLMError, LLMInvalidResponseError
from ranah_llm.models import (
    GenerateRequest,
    GenerateResult,
    Message,
    StructuredGenerateRequest,
    StructuredGenerateResult,
)
from ranah_llm.providers.base import LLMProvider
from ranah_llm.routing import ModelRouter, ModelTier

TraceHook = Callable[[str, dict[str, object]], None]
_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


def _noop_trace(event: str, data: dict[str, object]) -> None:
    return None


class LLMGateway:
    def __init__(
        self,
        providers: dict[str, LLMProvider],
        router: ModelRouter,
        *,
        trace_hook: TraceHook = _noop_trace,
    ) -> None:
        self._providers = providers
        self._router = router
        self._trace = trace_hook

    def _provider(self, name: str) -> LLMProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise ValueError(f"No provider registered under name {name!r}") from None

    async def generate(
        self,
        tier: ModelTier,
        messages: list[Message],
        *,
        agent_run_id: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> GenerateResult:
        route = self._router.resolve(tier)
        provider = self._provider(route.provider)
        request = GenerateRequest(
            messages=messages,
            model=route.model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            agent_run_id=agent_run_id,
        )
        self._trace("gateway.generate", {"tier": tier, "provider": provider.name, **_ctx(request)})
        try:
            result = await provider.generate(request)
        except LLMError as exc:
            self._trace("gateway.error", {"tier": tier, "error": type(exc).__name__})
            raise
        self._trace("gateway.usage", {"tier": tier, "usage": result.usage.model_dump()})
        return result

    async def generate_structured(
        self,
        tier: ModelTier,
        messages: list[Message],
        response_model: type[_SchemaT],
        *,
        agent_run_id: str | None = None,
        temperature: float = 0.2,
        result_hook: Callable[[StructuredGenerateResult], None] | None = None,
    ) -> _SchemaT:
        route = self._router.resolve(tier)
        provider = self._provider(route.provider)
        request = StructuredGenerateRequest(
            messages=messages,
            model=route.model,
            response_schema=response_model.model_json_schema(),
            schema_name=response_model.__name__,
            temperature=temperature,
            agent_run_id=agent_run_id,
        )
        self._trace(
            "gateway.generate_structured",
            {"tier": tier, "provider": provider.name, **_ctx(request)},
        )
        try:
            result: StructuredGenerateResult = await provider.generate_structured(request)
        except LLMError as exc:
            self._trace("gateway.error", {"tier": tier, "error": type(exc).__name__})
            raise
        self._trace("gateway.usage", {"tier": tier, "usage": result.usage.model_dump()})
        if result_hook is not None:
            result_hook(result)
        try:
            return response_model.model_validate(result.data)
        except ValidationError as exc:
            raise LLMInvalidResponseError(str(exc)) from exc


def _ctx(request: GenerateRequest | StructuredGenerateRequest) -> dict[str, object]:
    return {"model": request.model, "agent_run_id": request.agent_run_id}

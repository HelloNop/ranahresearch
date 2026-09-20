"""OpenAI provider. The only file in this codebase allowed to import the OpenAI SDK."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from ranah_llm.errors import (
    LLMAuthError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from ranah_llm.models import (
    GenerateRequest,
    GenerateResult,
    Message,
    ModelInfo,
    StructuredGenerateRequest,
    StructuredGenerateResult,
    Usage,
)
from ranah_llm.providers.base import LLMProvider

TraceHook = Callable[[str, dict[str, object]], None]
CostHook = Callable[[str, Usage], float | None]


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = dict(schema)
    result.pop("default", None)
    for key, value in result.items():
        if isinstance(value, dict):
            result[key] = (
                {
                    name: strict_schema(item) if isinstance(item, dict) else item
                    for name, item in value.items()
                }
                if key in ("properties", "$defs")
                else strict_schema(value)
            )
        elif isinstance(value, list):
            result[key] = [
                strict_schema(item) if isinstance(item, dict) else item for item in value
            ]
    if "properties" in result:
        result["required"] = list(result["properties"])
        result["additionalProperties"] = False
    return result


def _to_openai_messages(messages: list[Message]) -> list[ChatCompletionMessageParam]:
    # The SDK's message TypedDict union is a moving target across versions;
    # a plain role/content dict is valid at runtime for every role we send.
    return [{"role": m.role.value, "content": m.content} for m in messages]  # type: ignore[misc]


def _noop_trace(event: str, data: dict[str, object]) -> None:
    return None


def _no_cost(model: str, usage: Usage) -> float | None:
    return None


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        trace_hook: TraceHook = _noop_trace,
        cost_hook: CostHook = _no_cost,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._max_retries = max_retries
        self._trace = trace_hook
        self._cost = cost_hook

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        response = await self._with_retry(
            request.agent_run_id,
            "generate",
            lambda: self._client.chat.completions.create(
                model=request.model,
                messages=_to_openai_messages(request.messages),
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
            ),
        )
        choice = response.choices[0]
        return GenerateResult(
            text=choice.message.content or "",
            model=ModelInfo(provider=self.name, model=request.model),
            usage=self._usage_from(request.model, response.usage),
            finish_reason="stop" if choice.finish_reason == "stop" else "length",
        )

    async def generate_structured(
        self, request: StructuredGenerateRequest
    ) -> StructuredGenerateResult:
        response = await self._with_retry(
            request.agent_run_id,
            "generate_structured",
            lambda: self._client.chat.completions.create(
                model=request.model,
                messages=_to_openai_messages(request.messages),
                temperature=request.temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "schema": strict_schema(request.response_schema),
                        "strict": True,
                    },
                },
            ),
        )
        raw = response.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(f"model returned invalid JSON: {exc}") from exc
        return StructuredGenerateResult(
            data=data,
            model=ModelInfo(provider=self.name, model=request.model),
            usage=self._usage_from(request.model, response.usage),
        )

    def _usage_from(self, model: str, usage: object) -> Usage:
        result = Usage(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )
        result.estimated_cost = self._cost(model, result)
        return result

    async def _with_retry(
        self,
        agent_run_id: str | None,
        op: str,
        call: Callable[[], Awaitable[ChatCompletion]],
    ) -> ChatCompletion:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._trace("llm.request", {"op": op, "attempt": attempt, "agent_run_id": agent_run_id})
            try:
                response = await call()
                self._trace(
                    "llm.response", {"op": op, "attempt": attempt, "agent_run_id": agent_run_id}
                )
                return response
            except openai.AuthenticationError as exc:
                raise LLMAuthError(str(exc)) from exc
            except openai.APIStatusError as exc:
                if exc.status_code < 500 and not isinstance(exc, openai.RateLimitError):
                    raise LLMProviderError(str(exc)) from exc
                last_error = exc
            except (openai.APITimeoutError, openai.APIConnectionError) as exc:
                last_error = exc
            self._trace("llm.retry", {"op": op, "attempt": attempt, "agent_run_id": agent_run_id})
            await asyncio.sleep(min(2**attempt, 10))
        assert last_error is not None
        if isinstance(last_error, openai.APITimeoutError):
            raise LLMTimeoutError(str(last_error)) from last_error
        if isinstance(last_error, openai.RateLimitError):
            raise LLMRateLimitError(str(last_error)) from last_error
        raise LLMProviderError(str(last_error)) from last_error

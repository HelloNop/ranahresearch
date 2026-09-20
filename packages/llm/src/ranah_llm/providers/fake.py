"""Deterministic in-memory provider. No network; used by tests and the sample agent."""

import json
from collections.abc import Callable

from ranah_llm.errors import LLMInvalidResponseError, LLMProviderError
from ranah_llm.models import (
    EmbedRequest,
    EmbedResult,
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StructuredGenerateRequest,
    StructuredGenerateResult,
    Usage,
)
from ranah_llm.providers.base import LLMProvider


class FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(
        self,
        *,
        text_response: str = "fake response",
        structured_response: dict[str, object] | None = None,
        structured_response_fn: Callable[[StructuredGenerateRequest], dict[str, object]]
        | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self._text_response = text_response
        self._structured_response = structured_response or {}
        self._structured_response_fn = structured_response_fn
        self._fail_with = fail_with
        self.calls: list[GenerateRequest | StructuredGenerateRequest] = []

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        self.calls.append(request)
        if self._fail_with is not None:
            raise self._fail_with
        return GenerateResult(
            text=self._text_response,
            model=ModelInfo(provider=self.name, model=request.model),
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    async def generate_structured(
        self, request: StructuredGenerateRequest
    ) -> StructuredGenerateResult:
        self.calls.append(request)
        if self._fail_with is not None:
            raise self._fail_with
        data = (
            self._structured_response_fn(request)
            if self._structured_response_fn
            else self._structured_response
        )
        try:
            json.dumps(data)
        except TypeError as exc:
            raise LLMInvalidResponseError(str(exc)) from exc
        return StructuredGenerateResult(
            data=data,
            model=ModelInfo(provider=self.name, model=request.model),
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    async def embed(self, request: EmbedRequest) -> EmbedResult:
        if self._fail_with is not None:
            raise LLMProviderError(str(self._fail_with))
        return EmbedResult(
            vectors=[[0.0] * 3 for _ in request.texts],
            model=ModelInfo(provider=self.name, model=request.model),
            usage=Usage(input_tokens=len(request.texts)),
        )

"""Provider interface. Business logic never imports a concrete provider directly."""

from abc import ABC, abstractmethod

from ranah_llm.models import (
    EmbedRequest,
    EmbedResult,
    GenerateRequest,
    GenerateResult,
    StructuredGenerateRequest,
    StructuredGenerateResult,
)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...

    @abstractmethod
    async def generate_structured(
        self, request: StructuredGenerateRequest
    ) -> StructuredGenerateResult: ...

    async def embed(self, request: EmbedRequest) -> EmbedResult:
        raise NotImplementedError(f"{self.name} does not support embed()")

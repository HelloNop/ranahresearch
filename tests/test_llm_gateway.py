"""EPIC-006 acceptance tests. No paid API call: everything runs against FakeLLMProvider."""

import pytest
from pydantic import BaseModel
from ranah_llm.errors import LLMInvalidResponseError, LLMProviderError
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import Message, Role
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel


class Extraction(BaseModel):
    title: str
    year: int


def _gateway(provider: FakeLLMProvider) -> LLMGateway:
    router = ModelRouter({ModelTier.STANDARD: RoutedModel(provider="fake", model="fake-1")})
    return LLMGateway({"fake": provider}, router)


async def test_generate_returns_text_and_usage() -> None:
    provider = FakeLLMProvider(text_response="hello")
    gateway = _gateway(provider)
    result = await gateway.generate(
        ModelTier.STANDARD, [Message(role=Role.USER, content="hi")], agent_run_id="run-1"
    )
    assert result.text == "hello"
    assert result.model.provider == "fake"
    assert result.usage.input_tokens == 10
    assert provider.calls[0].agent_run_id == "run-1"


async def test_generate_structured_validates_against_schema() -> None:
    provider = FakeLLMProvider(structured_response={"title": "A paper", "year": 2024})
    gateway = _gateway(provider)
    result = await gateway.generate_structured(
        ModelTier.STANDARD, [Message(role=Role.USER, content="extract")], Extraction
    )
    assert result == Extraction(title="A paper", year=2024)


async def test_generate_structured_rejects_schema_mismatch() -> None:
    provider = FakeLLMProvider(structured_response={"title": "A paper"})  # missing "year"
    gateway = _gateway(provider)
    with pytest.raises(LLMInvalidResponseError):
        await gateway.generate_structured(
            ModelTier.STANDARD, [Message(role=Role.USER, content="extract")], Extraction
        )


async def test_provider_error_translation_propagates() -> None:
    provider = FakeLLMProvider(fail_with=LLMProviderError("boom"))
    gateway = _gateway(provider)
    with pytest.raises(LLMProviderError):
        await gateway.generate(ModelTier.STANDARD, [Message(role=Role.USER, content="hi")])


async def test_router_raises_for_unconfigured_tier() -> None:
    provider = FakeLLMProvider()
    gateway = _gateway(provider)
    with pytest.raises(ValueError, match="HIGH_REASONING"):
        await gateway.generate(ModelTier.HIGH_REASONING, [Message(role=Role.USER, content="hi")])

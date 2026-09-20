"""EPIC-008 acceptance tests: shared AcademicProvider contract + capability enforcement.

`assert_provider_contract` is the reusable suite EPIC-009 should run against every
real provider once it lands; for now only FakeAcademicProvider implements enough
to pass it.
"""

import pytest
from ranah_literature.errors import ProviderNotFoundError, UnsupportedCapabilityError
from ranah_literature.models import (
    ProviderCapability,
    ProviderIdentifier,
    ProviderIdentifierType,
    ProviderWork,
    SearchRequest,
)
from ranah_literature.providers.base import AcademicProvider
from ranah_literature.providers.crossref import CrossrefProvider
from ranah_literature.providers.fake import FakeAcademicProvider
from ranah_literature.providers.openalex import OpenAlexProvider
from ranah_literature.providers.semantic_scholar import SemanticScholarProvider


async def assert_provider_contract(provider: AcademicProvider, sample: ProviderWork) -> None:
    # search returns SearchPage; work IDs are preserved end to end.
    page = await provider.search(SearchRequest(query=sample.title))
    assert page.items
    assert page.items[0].provider_id == sample.provider_id

    # empty results are handled, not an error.
    empty = await provider.search(SearchRequest(query="no such title anywhere"))
    assert empty.items == []

    # DOI normalization is consistent regardless of how the DOI is written.
    assert sample.doi is not None
    fetched = await provider.get_by_doi(sample.doi.upper())
    assert fetched is not None
    assert fetched.provider_id == sample.provider_id

    # provider errors are normalized to ranah_literature.errors, not raw exceptions.
    with pytest.raises(ProviderNotFoundError):
        await provider.get_work("does-not-exist")


@pytest.fixture
def sample_work() -> ProviderWork:
    return ProviderWork(
        provider="fake",
        provider_id="W1",
        doi="10.1000/xyz123",
        title="Deep Learning for Systematic Reviews",
        identifiers=[
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.DOI, identifier="10.1000/xyz123"
            )
        ],
    )


async def test_fake_provider_satisfies_contract(sample_work: ProviderWork) -> None:
    provider = FakeAcademicProvider([sample_work])
    await assert_provider_contract(provider, sample_work)


async def test_capabilities_are_respected(sample_work: ProviderWork) -> None:
    restricted = FakeAcademicProvider(
        [sample_work],
        capabilities=ProviderCapability(can_get_references=False, can_get_citations=False),
    )
    with pytest.raises(UnsupportedCapabilityError):
        await restricted.get_references(sample_work.provider_id)
    with pytest.raises(UnsupportedCapabilityError):
        await restricted.get_citations(sample_work.provider_id)

    permissive = FakeAcademicProvider([sample_work])
    assert await permissive.get_references(sample_work.provider_id) == []
    assert await permissive.get_citations(sample_work.provider_id) == []


async def test_all_three_epic009_providers_declare_capabilities() -> None:
    # See test_literature_provider_contract.py for the real providers actually
    # running assert_provider_contract() above against mocked HTTP responses.
    for provider_cls in (CrossrefProvider, OpenAlexProvider, SemanticScholarProvider):
        provider = provider_cls(http=None)  # type: ignore[arg-type]
        assert isinstance(provider.capabilities, ProviderCapability)

"""In-memory provider: no network. Used by the shared contract test suite and by callers
that need a literature provider before EPIC-009 lands the real ones."""

from ranah_literature.errors import ProviderNotFoundError
from ranah_literature.models import (
    ProviderCapability,
    ProviderWork,
    SearchPage,
    SearchRequest,
)
from ranah_literature.normalization import normalize_doi
from ranah_literature.providers.base import AcademicProvider


class FakeAcademicProvider(AcademicProvider):
    name = "fake"

    def __init__(
        self,
        works: list[ProviderWork] | None = None,
        *,
        capabilities: ProviderCapability | None = None,
    ) -> None:
        self._works = works or []
        self.capabilities = capabilities or ProviderCapability(
            can_get_references=True, can_get_citations=True
        )

    async def search(self, request: SearchRequest) -> SearchPage:
        matches = [w for w in self._works if request.query.lower() in w.title.lower()]
        return SearchPage(items=matches, next_cursor=None, total_estimated=len(matches))

    async def get_work(self, provider_id: str) -> ProviderWork:
        for work in self._works:
            if work.provider_id == provider_id:
                return work
        raise ProviderNotFoundError(f"no work with id {provider_id}")

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        target = normalize_doi(doi)
        for work in self._works:
            if work.doi and normalize_doi(work.doi) == target:
                return work
        return None

    async def get_references(self, provider_id: str) -> list[ProviderWork]:
        if not self.capabilities.can_get_references:
            return await super().get_references(provider_id)
        return []

    async def get_citations(self, provider_id: str) -> list[ProviderWork]:
        if not self.capabilities.can_get_citations:
            return await super().get_citations(provider_id)
        return []

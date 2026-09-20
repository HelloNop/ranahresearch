"""Semantic Scholar: discovery/enrichment/citation graph. Foundation only; EPIC-009 adapts it.

See docs/OPENDRAFT_ADOPTION.md #7 for what's planned to be adapted from
OpenDraft's `engine/utils/api_citations/semantic_scholar.py`: Graph API, DOI
identifier syntax, external IDs, citations, rewritten for paginated results.
"""

from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import ProviderCapability, ProviderWork, SearchPage, SearchRequest
from ranah_literature.providers.base import AcademicProvider

CAPABILITIES = ProviderCapability(can_get_references=True, can_get_citations=True)


class SemanticScholarProvider(AcademicProvider):
    name = "semantic_scholar"
    capabilities = CAPABILITIES

    def __init__(self, http: ProviderHTTPClient) -> None:
        self._http = http

    async def search(self, request: SearchRequest) -> SearchPage:
        raise NotImplementedError("SemanticScholarProvider.search lands in EPIC-009")

    async def get_work(self, provider_id: str) -> ProviderWork:
        raise NotImplementedError("SemanticScholarProvider.get_work lands in EPIC-009")

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        raise NotImplementedError("SemanticScholarProvider.get_by_doi lands in EPIC-009")

    async def get_references(self, provider_id: str) -> list[ProviderWork]:
        raise NotImplementedError("SemanticScholarProvider.get_references lands in EPIC-009")

    async def get_citations(self, provider_id: str) -> list[ProviderWork]:
        raise NotImplementedError("SemanticScholarProvider.get_citations lands in EPIC-009")

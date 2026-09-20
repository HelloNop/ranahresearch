"""OpenAlex: discovery/citation graph. Foundation only; full adaptation is EPIC-009.

See docs/OPENDRAFT_ADOPTION.md #6 for what's planned to be adapted from
OpenDraft's `engine/utils/api_citations/openalex.py`: abstract inverted-index
reconstruction, DOI/authors/year/venue/citation count/work type, extended
with get_references/get_citations.
"""

from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import ProviderCapability, ProviderWork, SearchPage, SearchRequest
from ranah_literature.providers.base import AcademicProvider

CAPABILITIES = ProviderCapability(can_get_references=True, can_get_citations=True)


class OpenAlexProvider(AcademicProvider):
    name = "openalex"
    capabilities = CAPABILITIES

    def __init__(self, http: ProviderHTTPClient) -> None:
        self._http = http

    async def search(self, request: SearchRequest) -> SearchPage:
        raise NotImplementedError("OpenAlexProvider.search lands in EPIC-009")

    async def get_work(self, provider_id: str) -> ProviderWork:
        raise NotImplementedError("OpenAlexProvider.get_work lands in EPIC-009")

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        raise NotImplementedError("OpenAlexProvider.get_by_doi lands in EPIC-009")

    async def get_references(self, provider_id: str) -> list[ProviderWork]:
        raise NotImplementedError("OpenAlexProvider.get_references lands in EPIC-009")

    async def get_citations(self, provider_id: str) -> list[ProviderWork]:
        raise NotImplementedError("OpenAlexProvider.get_citations lands in EPIC-009")

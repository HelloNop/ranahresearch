"""Crossref: DOI/metadata authority. Foundation only; full adaptation is EPIC-009.

See docs/OPENDRAFT_ADOPTION.md #5 for what's planned to be adapted from
OpenDraft's `engine/utils/api_citations/crossref.py`: /works search, DOI
lookup, JATS abstract cleanup, source-type mapping — rewritten async with
pagination and a full result set.
"""

from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import ProviderCapability, ProviderWork, SearchPage, SearchRequest
from ranah_literature.providers.base import AcademicProvider

CAPABILITIES = ProviderCapability(can_get_references=False, can_get_citations=False)


class CrossrefProvider(AcademicProvider):
    name = "crossref"
    capabilities = CAPABILITIES

    def __init__(self, http: ProviderHTTPClient) -> None:
        self._http = http

    async def search(self, request: SearchRequest) -> SearchPage:
        raise NotImplementedError("CrossrefProvider.search lands in EPIC-009")

    async def get_work(self, provider_id: str) -> ProviderWork:
        raise NotImplementedError("CrossrefProvider.get_work lands in EPIC-009")

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        raise NotImplementedError("CrossrefProvider.get_by_doi lands in EPIC-009")

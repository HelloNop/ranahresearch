"""Semantic Scholar: discovery/enrichment/citation graph.

OpenDraft's `engine/utils/api_citations/semantic_scholar.py` is the documented
reference point (docs/OPENDRAFT_ADOPTION.md #7), but that source is not
available in this repository or environment. This is an independent
implementation against the public Semantic Scholar Graph API, following the
documented behavior (externalIds, paper ID, paginated results) rather than
any copied code.
"""

from typing import Any

from ranah_literature.errors import ProviderNotFoundError
from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import (
    ProviderAuthor,
    ProviderCapability,
    ProviderIdentifier,
    ProviderIdentifierType,
    ProviderWork,
    SearchPage,
    SearchRequest,
)
from ranah_literature.normalization import split_display_name
from ranah_literature.providers.base import AcademicProvider

CAPABILITIES = ProviderCapability(can_get_references=True, can_get_citations=True)

_FIELDS = (
    "paperId,externalIds,title,abstract,year,venue,publicationDate,"
    "authors,citationCount,publicationTypes,url"
)


def _map_author(raw: dict[str, Any]) -> ProviderAuthor:
    # The Graph API reports a single display name, not given/family separately.
    name = raw.get("name") or "Unknown"
    given, family = split_display_name(name)
    return ProviderAuthor(display_name=name, given_name=given, family_name=family)


def map_semantic_scholar_paper(item: dict[str, Any]) -> ProviderWork:
    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI")

    identifiers = []
    if doi:
        identifiers.append(
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi)
        )
    if external_ids.get("PubMed"):
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.PMID,
                identifier=str(external_ids["PubMed"]),
            )
        )
    if external_ids.get("PubMedCentral"):
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.PMCID,
                identifier=str(external_ids["PubMedCentral"]),
            )
        )
    if external_ids.get("ArXiv"):
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.ARXIV_ID,
                identifier=str(external_ids["ArXiv"]),
            )
        )
    paper_id = item.get("paperId") or ""
    if paper_id:
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.SEMANTIC_SCHOLAR_ID, identifier=paper_id
            )
        )

    publication_types = item.get("publicationTypes") or []
    return ProviderWork(
        provider="semantic_scholar",
        provider_id=paper_id,
        doi=doi,
        title=item.get("title") or "Untitled",
        abstract=item.get("abstract"),
        authors=[_map_author(a) for a in item.get("authors") or []],
        publication_year=item.get("year"),
        publication_date=item.get("publicationDate"),
        venue=item.get("venue"),
        url=item.get("url"),
        work_type=publication_types[0] if publication_types else None,
        citation_count=item.get("citationCount"),
        identifiers=identifiers,
        raw_metadata=item,
    )


class SemanticScholarProvider(AcademicProvider):
    name = "semantic_scholar"
    capabilities = CAPABILITIES

    def __init__(self, http: ProviderHTTPClient) -> None:
        self._http = http

    async def search(self, request: SearchRequest) -> SearchPage:
        offset = int(request.cursor) if request.cursor else 0
        params = {
            "query": request.query,
            "offset": offset,
            "limit": request.page_size,
            "fields": _FIELDS,
        }
        if "year" in request.filters:
            params["year"] = request.filters["year"]
        payload = await self._http.get_json("/paper/search", params=params)
        items = [map_semantic_scholar_paper(item) for item in payload.get("data", [])]
        next_offset = payload.get("next")
        return SearchPage(
            items=items,
            next_cursor=str(next_offset) if next_offset is not None else None,
            total_estimated=payload.get("total"),
        )

    async def get_work(self, provider_id: str) -> ProviderWork:
        payload = await self._http.get_json(f"/paper/{provider_id}", params={"fields": _FIELDS})
        return map_semantic_scholar_paper(payload)

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        try:
            payload = await self._http.get_json(f"/paper/DOI:{doi}", params={"fields": _FIELDS})
        except ProviderNotFoundError:
            return None
        return map_semantic_scholar_paper(payload)

    async def get_references(self, provider_id: str) -> list[ProviderWork]:
        payload = await self._http.get_json(
            f"/paper/{provider_id}/references", params={"fields": f"citedPaper.{_FIELDS}"}
        )
        return [
            map_semantic_scholar_paper(item["citedPaper"])
            for item in payload.get("data", [])
            if item.get("citedPaper")
        ]

    async def get_citations(self, provider_id: str) -> list[ProviderWork]:
        payload = await self._http.get_json(
            f"/paper/{provider_id}/citations", params={"fields": f"citingPaper.{_FIELDS}"}
        )
        return [
            map_semantic_scholar_paper(item["citingPaper"])
            for item in payload.get("data", [])
            if item.get("citingPaper")
        ]

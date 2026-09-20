"""OpenAlex: discovery/citation graph.

OpenDraft's `engine/utils/api_citations/openalex.py` is the documented
reference point (docs/OPENDRAFT_ADOPTION.md #6), but that source is not
available in this repository or environment. This is an independent
implementation against OpenAlex's public REST API, following the documented
behavior (abstract inverted-index reconstruction, DOI/authors/year/venue/
citation-count/work-type extraction, extended with get_references/
get_citations) rather than any copied code.
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
from ranah_literature.providers.base import AcademicProvider

CAPABILITIES = ProviderCapability(can_get_references=True, can_get_citations=True)


def _short_id(full_id: str | None) -> str | None:
    if not full_id:
        return None
    return full_id.rstrip("/").rsplit("/", 1)[-1]


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex ships abstracts as a word -> [positions] inverted index, not plain text."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, indices in inverted_index.items():
        for idx in indices:
            positions[idx] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def _map_author(authorship: dict[str, Any]) -> ProviderAuthor:
    author = authorship.get("author") or {}
    display = author.get("display_name") or "Unknown"
    return ProviderAuthor(display_name=display, orcid=_short_id(author.get("orcid")))


def map_openalex_work(item: dict[str, Any]) -> ProviderWork:
    ids = item.get("ids") or {}
    doi = ids.get("doi")
    if doi and "doi.org/" in doi:
        doi = doi.rsplit("doi.org/", 1)[-1]
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or item.get("host_venue") or {}

    identifiers = []
    if doi:
        identifiers.append(
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi)
        )
    openalex_id = _short_id(item.get("id"))
    if openalex_id:
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.OPENALEX_ID, identifier=openalex_id
            )
        )
    if ids.get("pmid"):
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.PMID, identifier=_short_id(ids["pmid"]) or ""
            )
        )
    if ids.get("pmcid"):
        identifiers.append(
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.PMCID,
                identifier=_short_id(ids["pmcid"]) or "",
            )
        )

    return ProviderWork(
        provider="openalex",
        provider_id=openalex_id or "",
        doi=doi,
        title=item.get("title") or item.get("display_name") or "Untitled",
        abstract=reconstruct_abstract(item.get("abstract_inverted_index")),
        authors=[_map_author(a) for a in item.get("authorships") or []],
        publication_year=item.get("publication_year"),
        publication_date=item.get("publication_date"),
        venue=source.get("display_name"),
        publisher=source.get("host_organization_name"),
        url=primary_location.get("landing_page_url"),
        work_type=item.get("type"),
        citation_count=item.get("cited_by_count"),
        identifiers=identifiers,
        raw_metadata=item,
    )


class OpenAlexProvider(AcademicProvider):
    name = "openalex"
    capabilities = CAPABILITIES

    def __init__(self, http: ProviderHTTPClient) -> None:
        self._http = http

    async def search(self, request: SearchRequest) -> SearchPage:
        params: dict[str, Any] = {
            "search": request.query,
            "per-page": request.page_size,
            "cursor": request.cursor or "*",
        }
        if request.filters:
            params["filter"] = ",".join(f"{k}:{v}" for k, v in request.filters.items())
        payload = await self._http.get_json("/works", params=params)
        items = [map_openalex_work(item) for item in payload.get("results", [])]
        meta = payload.get("meta", {})
        return SearchPage(
            items=items,
            next_cursor=meta.get("next_cursor") if items else None,
            total_estimated=meta.get("count"),
        )

    async def get_work(self, provider_id: str) -> ProviderWork:
        payload = await self._http.get_json(f"/works/{provider_id}")
        return map_openalex_work(payload)

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        try:
            payload = await self._http.get_json(f"/works/doi:{doi}")
        except ProviderNotFoundError:
            return None
        return map_openalex_work(payload)

    async def get_references(self, provider_id: str) -> list[ProviderWork]:
        work = await self.get_work(provider_id)
        referenced_ids = work.raw_metadata.get("referenced_works") or []
        results: list[ProviderWork] = []
        for ref_id in referenced_ids:
            short = _short_id(ref_id)
            if not short:
                continue
            try:
                results.append(await self.get_work(short))
            except ProviderNotFoundError:
                continue
        return results

    async def get_citations(self, provider_id: str) -> list[ProviderWork]:
        payload = await self._http.get_json("/works", params={"filter": f"cites:{provider_id}"})
        return [map_openalex_work(item) for item in payload.get("results", [])]

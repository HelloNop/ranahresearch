"""Crossref: DOI/metadata authority.

OpenDraft's `engine/utils/api_citations/crossref.py` is the documented
reference point (docs/OPENDRAFT_ADOPTION.md #5), but that source is not
available in this repository or environment. This is an independent
implementation against Crossref's public REST API (`/works`), following the
*documented* behavior (title/author/date/venue extraction, JATS abstract
cleanup, source-type mapping) rather than any copied code — see the
completion report's "OpenDraft Adoption" section for the precise PORT/ADAPT/
REFERENCE classification.
"""

import re
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

CAPABILITIES = ProviderCapability(can_get_references=False, can_get_citations=False)

_JATS_TAG_RE = re.compile(r"</?jats:[^>]+>")


def _clean_abstract(raw: str | None) -> str | None:
    """Crossref abstracts are JATS-tagged XML fragments; strip the tags, keep the text."""
    if not raw:
        return None
    text = _JATS_TAG_RE.sub(" ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _date_parts(container: dict[str, Any] | None) -> list[int] | None:
    if not container:
        return None
    parts = container.get("date-parts")
    if not parts or not parts[0] or parts[0][0] is None:
        return None
    return list(parts[0])


def _extract_year(container: dict[str, Any] | None) -> int | None:
    parts = _date_parts(container)
    return parts[0] if parts else None


def _extract_date(container: dict[str, Any] | None) -> str | None:
    parts = _date_parts(container)
    if not parts:
        return None
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _map_author(raw: dict[str, Any]) -> ProviderAuthor:
    given = raw.get("given")
    family = raw.get("family")
    display = " ".join(p for p in (given, family) if p) or raw.get("name") or "Unknown"
    orcid = raw.get("ORCID")
    if orcid:
        orcid = orcid.rstrip("/").rsplit("/", 1)[-1]
    return ProviderAuthor(display_name=display, given_name=given, family_name=family, orcid=orcid)


def map_crossref_item(item: dict[str, Any]) -> ProviderWork:
    doi = item.get("DOI")
    titles = item.get("title") or []
    title = titles[0] if titles else "Untitled"
    containers = item.get("container-title") or []
    venue = containers[0] if containers else None
    date_container = (
        item.get("published-print")
        or item.get("published-online")
        or item.get("published")
        or item.get("issued")
    )

    identifiers = []
    if doi:
        identifiers.append(
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi)
        )

    return ProviderWork(
        provider="crossref",
        provider_id=doi or item.get("URL") or "",
        doi=doi,
        title=title,
        abstract=_clean_abstract(item.get("abstract")),
        authors=[_map_author(a) for a in item.get("author") or []],
        publication_year=_extract_year(date_container),
        publication_date=_extract_date(date_container),
        venue=venue,
        publisher=item.get("publisher"),
        volume=item.get("volume"),
        issue=item.get("issue"),
        pages=item.get("page"),
        url=item.get("URL"),
        work_type=item.get("type"),
        citation_count=item.get("is-referenced-by-count"),
        identifiers=identifiers,
        raw_metadata=item,
    )


def _crossref_params(request: SearchRequest, offset: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query.bibliographic": request.query,
        "rows": request.page_size,
        "offset": offset,
    }
    if request.filters:
        # Provider-specific pass-through: caller supplies Crossref filter keys directly
        # (e.g. {"from-pub-date": "2020-01-01", "type": "journal-article"}).
        params["filter"] = ",".join(f"{k}:{v}" for k, v in request.filters.items())
    return params


class CrossrefProvider(AcademicProvider):
    name = "crossref"
    capabilities = CAPABILITIES

    def __init__(self, http: ProviderHTTPClient) -> None:
        self._http = http

    async def search(self, request: SearchRequest) -> SearchPage:
        offset = int(request.cursor) if request.cursor else 0
        payload = await self._http.get_json("/works", params=_crossref_params(request, offset))
        message = payload.get("message", {})
        items = [map_crossref_item(item) for item in message.get("items", [])]
        total = message.get("total-results")
        next_offset = offset + len(items)
        has_more = items and total is not None and next_offset < total
        return SearchPage(
            items=items,
            next_cursor=str(next_offset) if has_more else None,
            total_estimated=total,
        )

    async def get_work(self, provider_id: str) -> ProviderWork:
        # Crossref's natural key is the DOI, so get_work and get_by_doi overlap here.
        work = await self.get_by_doi(provider_id)
        if work is None:
            raise ProviderNotFoundError(f"crossref work not found: {provider_id}")
        return work

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        try:
            payload = await self._http.get_json(f"/works/{doi}")
        except ProviderNotFoundError:
            return None
        return map_crossref_item(payload["message"])

"""EPIC-009 acceptance test: the real providers pass the exact same shared
AcademicProvider contract suite that FakeAcademicProvider passes
(test_literature_contract.py::assert_provider_contract). No network: each
provider gets an httpx.MockTransport that answers like the real API would.
"""

from typing import Any

import httpx
from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import ProviderWork
from ranah_literature.providers.crossref import CrossrefProvider
from ranah_literature.providers.openalex import OpenAlexProvider
from ranah_literature.providers.semantic_scholar import SemanticScholarProvider
from test_literature_contract import assert_provider_contract


def _mock_client(handler: httpx.MockTransport) -> ProviderHTTPClient:
    http = ProviderHTTPClient("https://example.test", backoff_base_seconds=0.01)
    http._client = httpx.AsyncClient(base_url="https://example.test", transport=handler)
    return http


async def test_crossref_satisfies_shared_provider_contract() -> None:
    doi = "10.1000/xyz123"
    item: dict[str, Any] = {
        "DOI": doi,
        "title": ["Deep Learning for Systematic Reviews"],
        "author": [{"given": "Jane", "family": "Doe"}],
        "type": "journal-article",
    }
    sample = ProviderWork(provider="crossref", provider_id=doi, doi=doi, title=item["title"][0])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/works/"):
            requested_doi = request.url.path.removeprefix("/works/")
            if requested_doi.lower() == doi.lower():
                return httpx.Response(200, json={"status": "ok", "message": item})
            return httpx.Response(404)
        query = request.url.params.get("query.bibliographic", "")
        matches = [item] if "deep learning" in query.lower() else []
        return httpx.Response(
            200, json={"status": "ok", "message": {"total-results": len(matches), "items": matches}}
        )

    provider = CrossrefProvider(_mock_client(httpx.MockTransport(handler)))
    await assert_provider_contract(provider, sample)


async def test_openalex_satisfies_shared_provider_contract() -> None:
    doi = "10.1000/xyz123"
    work: dict[str, Any] = {
        "id": "https://openalex.org/W1",
        "ids": {"openalex": "https://openalex.org/W1", "doi": f"https://doi.org/{doi}"},
        "title": "Deep Learning for Systematic Reviews",
        "authorships": [],
        "type": "article",
    }
    sample = ProviderWork(provider="openalex", provider_id="W1", doi=doi, title=work["title"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/works/does-not-exist":
            return httpx.Response(404)
        if request.url.path.startswith("/works/doi:"):
            requested_doi = request.url.path.removeprefix("/works/doi:")
            if requested_doi.lower() == doi.lower():
                return httpx.Response(200, json=work)
            return httpx.Response(404)
        if request.url.path.startswith("/works/"):
            return httpx.Response(200, json=work)
        query = request.url.params.get("search", "")
        matches = [work] if "deep learning" in query.lower() else []
        return httpx.Response(200, json={"meta": {"count": len(matches)}, "results": matches})

    provider = OpenAlexProvider(_mock_client(httpx.MockTransport(handler)))
    await assert_provider_contract(provider, sample)


async def test_semantic_scholar_satisfies_shared_provider_contract() -> None:
    doi = "10.1000/xyz123"
    paper: dict[str, Any] = {
        "paperId": "abc123",
        "externalIds": {"DOI": doi},
        "title": "Deep Learning for Systematic Reviews",
        "authors": [],
    }
    sample = ProviderWork(
        provider="semantic_scholar", provider_id="abc123", doi=doi, title=paper["title"]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/paper/search":
            query = request.url.params.get("query", "")
            matches = [paper] if "deep learning" in query.lower() else []
            return httpx.Response(
                200, json={"total": len(matches), "offset": 0, "next": None, "data": matches}
            )
        if request.url.path == "/paper/does-not-exist":
            return httpx.Response(404)
        if request.url.path.startswith("/paper/DOI:"):
            requested_doi = request.url.path.removeprefix("/paper/DOI:")
            if requested_doi.lower() == doi.lower():
                return httpx.Response(200, json=paper)
            return httpx.Response(404)
        return httpx.Response(200, json=paper)

    provider = SemanticScholarProvider(_mock_client(httpx.MockTransport(handler)))
    await assert_provider_contract(provider, sample)

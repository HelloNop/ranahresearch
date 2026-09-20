"""EPIC-009 acceptance tests: real provider mapping + HTTP behavior, against
crafted fixture responses. No network: httpx.MockTransport stands in for the
real Crossref/OpenAlex/Semantic Scholar APIs, per each API's actual documented
response shape.
"""

from typing import Any

import httpx
import pytest
from ranah_literature.errors import (
    ProviderRateLimitError,
    ProviderResponseError,
)
from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import ProviderIdentifierType, SearchRequest
from ranah_literature.providers.crossref import CrossrefProvider, map_crossref_item
from ranah_literature.providers.openalex import (
    OpenAlexProvider,
    map_openalex_work,
    reconstruct_abstract,
)
from ranah_literature.providers.semantic_scholar import (
    SemanticScholarProvider,
    map_semantic_scholar_paper,
)


def _mock_client(handler: httpx.MockTransport) -> ProviderHTTPClient:
    http = ProviderHTTPClient("https://example.test", backoff_base_seconds=0.01)
    http._client = httpx.AsyncClient(base_url="https://example.test", transport=handler)
    return http


def _json_handler(payload: dict[str, Any], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler)


# --- Crossref ------------------------------------------------------------------

CROSSREF_NORMAL_ITEM = {
    "DOI": "10.1000/normal-article",
    "title": ["A Normal Journal Article"],
    "author": [
        {"given": "Jane", "family": "Doe", "ORCID": "http://orcid.org/0000-0001-2345-6789"},
        {"given": "John", "family": "Smith"},
    ],
    "container-title": ["Journal of Examples"],
    "publisher": "Example Press",
    "volume": "12",
    "issue": "3",
    "page": "100-110",
    "URL": "https://doi.org/10.1000/normal-article",
    "type": "journal-article",
    "abstract": "<jats:p>This is a <jats:italic>clean</jats:italic> abstract.</jats:p>",
    "is-referenced-by-count": 42,
    "published-print": {"date-parts": [[2022, 5, 1]]},
}

CROSSREF_MISSING_ABSTRACT_ITEM = {
    "DOI": "10.1000/no-abstract",
    "title": ["Missing Abstract Paper"],
    "author": [{"given": "A", "family": "Author"}],
    "type": "journal-article",
    "issued": {"date-parts": [[2021]]},
}

CROSSREF_MANY_AUTHORS_ITEM = {
    "DOI": "10.1000/many-authors",
    "title": ["A Paper With Many Authors"],
    "author": [{"given": f"First{i}", "family": f"Last{i}"} for i in range(8)],
    "type": "journal-article",
}

CROSSREF_UNICODE_ITEM = {
    "DOI": "10.1000/unicode",
    "title": ["Étude sur l'éducation générative en IA"],
    "author": [{"given": "José", "family": "Müller"}],
    "type": "journal-article",
}

CROSSREF_PREPRINT_ITEM = {
    "DOI": "10.1000/preprint",
    "title": ["A Preprint About Things"],
    "author": [{"given": "P", "family": "Reprint"}],
    "type": "posted-content",
}

CROSSREF_CONFERENCE_ITEM = {
    "DOI": "10.1000/conference",
    "title": ["Proceedings Paper"],
    "author": [{"given": "C", "family": "Author"}],
    "type": "proceedings-article",
    "container-title": ["Proc. of Examples Conference"],
}


def test_map_crossref_item_normal_article() -> None:
    work = map_crossref_item(CROSSREF_NORMAL_ITEM)
    assert work.provider == "crossref"
    assert work.doi == "10.1000/normal-article"
    assert work.title == "A Normal Journal Article"
    assert work.abstract == "This is a clean abstract."
    assert [a.family_name for a in work.authors] == ["Doe", "Smith"]
    assert work.authors[0].orcid == "0000-0001-2345-6789"
    assert work.venue == "Journal of Examples"
    assert work.publication_year == 2022
    assert work.publication_date == "2022-05-01"
    assert work.citation_count == 42
    assert work.work_type == "journal-article"
    assert work.raw_metadata == CROSSREF_NORMAL_ITEM
    assert any(i.identifier_type == ProviderIdentifierType.DOI for i in work.identifiers)


def test_map_crossref_item_missing_abstract() -> None:
    work = map_crossref_item(CROSSREF_MISSING_ABSTRACT_ITEM)
    assert work.abstract is None
    assert work.publication_year == 2021


def test_map_crossref_item_many_authors_preserved() -> None:
    work = map_crossref_item(CROSSREF_MANY_AUTHORS_ITEM)
    assert len(work.authors) == 8


def test_map_crossref_item_unicode() -> None:
    work = map_crossref_item(CROSSREF_UNICODE_ITEM)
    assert "Étude" in work.title
    assert work.authors[0].family_name == "Müller"


def test_map_crossref_item_preprint_and_conference_types() -> None:
    assert map_crossref_item(CROSSREF_PREPRINT_ITEM).work_type == "posted-content"
    assert map_crossref_item(CROSSREF_CONFERENCE_ITEM).work_type == "proceedings-article"


async def test_crossref_search_returns_search_page() -> None:
    payload = {
        "status": "ok",
        "message": {"total-results": 1, "items": [CROSSREF_NORMAL_ITEM]},
    }
    provider = CrossrefProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="normal article"))
    assert len(page.items) == 1
    assert page.items[0].provider_id == "10.1000/normal-article"
    assert page.next_cursor is None  # all results already retrieved


async def test_crossref_search_pagination_sets_next_cursor() -> None:
    payload = {
        "status": "ok",
        "message": {
            "total-results": 4,
            "items": [CROSSREF_NORMAL_ITEM, CROSSREF_MANY_AUTHORS_ITEM],
        },
    }
    provider = CrossrefProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="x", page_size=2))
    assert page.next_cursor == "2"


async def test_crossref_get_by_doi_not_found_returns_none() -> None:
    provider = CrossrefProvider(_mock_client(_json_handler({}, status=404)))
    assert await provider.get_by_doi("10.1000/missing") is None


async def test_crossref_search_empty_results() -> None:
    payload = {"status": "ok", "message": {"total-results": 0, "items": []}}
    provider = CrossrefProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="nothing matches this"))
    assert page.items == []


async def test_crossref_provider_error_is_normalized() -> None:
    provider = CrossrefProvider(_mock_client(_json_handler({}, status=429)))
    with pytest.raises(ProviderRateLimitError):
        await provider.search(SearchRequest(query="x"))


# --- OpenAlex --------------------------------------------------------------------


def test_reconstruct_abstract_from_inverted_index() -> None:
    index = {"Deep": [0], "learning": [1], "works": [2]}
    assert reconstruct_abstract(index) == "Deep learning works"


def test_reconstruct_abstract_handles_missing_index() -> None:
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


OPENALEX_NORMAL_WORK = {
    "id": "https://openalex.org/W2741809807",
    "ids": {
        "openalex": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.1000/openalex-normal",
        "pmid": "https://pubmed.ncbi.nlm.nih.gov/12345678",
    },
    "title": "An OpenAlex Work",
    "abstract_inverted_index": {"An": [0], "abstract": [1], "reconstructed": [2]},
    "publication_year": 2020,
    "publication_date": "2020-03-01",
    "primary_location": {
        "source": {"display_name": "OpenAlex Journal", "host_organization_name": "OA Press"},
        "landing_page_url": "https://example.org/work",
    },
    "authorships": [
        {"author": {"display_name": "Jane Doe", "orcid": "https://orcid.org/0000-0001-2345-6789"}},
    ],
    "type": "article",
    "cited_by_count": 7,
    "referenced_works": ["https://openalex.org/W2222", "https://openalex.org/W3333"],
}

OPENALEX_NO_DOI_WORK = {
    "id": "https://openalex.org/W9999",
    "ids": {"openalex": "https://openalex.org/W9999"},
    "title": "A Work Without a DOI",
    "publication_year": 2019,
    "authorships": [],
    "type": "preprint",
}


def test_map_openalex_work_normal() -> None:
    work = map_openalex_work(OPENALEX_NORMAL_WORK)
    assert work.provider_id == "W2741809807"
    assert work.doi == "10.1000/openalex-normal"
    assert work.abstract == "An abstract reconstructed"
    assert work.venue == "OpenAlex Journal"
    assert work.citation_count == 7
    assert any(i.identifier_type == ProviderIdentifierType.PMID for i in work.identifiers)


def test_map_openalex_work_missing_doi() -> None:
    work = map_openalex_work(OPENALEX_NO_DOI_WORK)
    assert work.doi is None
    assert work.provider_id == "W9999"
    assert work.work_type == "preprint"


async def test_openalex_search_returns_search_page() -> None:
    payload = {"meta": {"count": 1, "next_cursor": None}, "results": [OPENALEX_NORMAL_WORK]}
    provider = OpenAlexProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="openalex"))
    assert len(page.items) == 1
    assert page.items[0].doi == "10.1000/openalex-normal"


async def test_openalex_search_empty_results() -> None:
    payload = {"meta": {"count": 0, "next_cursor": None}, "results": []}
    provider = OpenAlexProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="nothing"))
    assert page.items == []
    assert page.next_cursor is None


async def test_openalex_get_by_doi_not_found() -> None:
    provider = OpenAlexProvider(_mock_client(_json_handler({}, status=404)))
    assert await provider.get_by_doi("10.1000/missing") is None


async def test_openalex_get_references_fetches_each_referenced_work() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("W2741809807"):
            return httpx.Response(200, json=OPENALEX_NORMAL_WORK)
        return httpx.Response(200, json=OPENALEX_NO_DOI_WORK)

    provider = OpenAlexProvider(_mock_client(httpx.MockTransport(handler)))
    refs = await provider.get_references("W2741809807")
    assert len(refs) == 2  # both referenced_works ids resolved


async def test_openalex_capabilities_declared() -> None:
    provider = OpenAlexProvider(_mock_client(_json_handler({})))
    assert provider.capabilities.can_get_references is True
    assert provider.capabilities.can_get_citations is True


# --- Semantic Scholar --------------------------------------------------------------

S2_NORMAL_PAPER = {
    "paperId": "abc123",
    "externalIds": {"DOI": "10.1000/s2-normal", "PubMed": "1234567"},
    "title": "A Semantic Scholar Paper",
    "abstract": "An abstract from Semantic Scholar.",
    "year": 2023,
    "venue": "S2 Venue",
    "publicationDate": "2023-06-15",
    "authors": [{"authorId": "1", "name": "Jane Q. Doe"}],
    "citationCount": 5,
    "publicationTypes": ["JournalArticle"],
    "url": "https://www.semanticscholar.org/paper/abc123",
}

S2_MULTIPLE_IDENTIFIERS_PAPER = {
    "paperId": "def456",
    "externalIds": {
        "DOI": "10.1000/s2-multi",
        "PubMed": "111",
        "PubMedCentral": "PMC222",
        "ArXiv": "2101.00001",
    },
    "title": "A Paper With Many External IDs",
    "authors": [],
}

S2_CONFERENCE_PAPER = {
    "paperId": "ghi789",
    "externalIds": {},
    "title": "A Conference Paper",
    "authors": [{"authorId": "2", "name": "Cher"}],
    "publicationTypes": ["Conference"],
}


def test_map_semantic_scholar_paper_normal() -> None:
    work = map_semantic_scholar_paper(S2_NORMAL_PAPER)
    assert work.provider_id == "abc123"
    assert work.doi == "10.1000/s2-normal"
    assert work.authors[0].given_name == "Jane Q."
    assert work.authors[0].family_name == "Doe"
    assert work.work_type == "JournalArticle"


def test_map_semantic_scholar_paper_multiple_identifiers() -> None:
    work = map_semantic_scholar_paper(S2_MULTIPLE_IDENTIFIERS_PAPER)
    types = {i.identifier_type for i in work.identifiers}
    assert types == {
        ProviderIdentifierType.DOI,
        ProviderIdentifierType.PMID,
        ProviderIdentifierType.PMCID,
        ProviderIdentifierType.ARXIV_ID,
        ProviderIdentifierType.SEMANTIC_SCHOLAR_ID,
    }


def test_map_semantic_scholar_paper_single_token_author_name() -> None:
    work = map_semantic_scholar_paper(S2_CONFERENCE_PAPER)
    assert work.authors[0].family_name == "Cher"
    assert work.doi is None


async def test_semantic_scholar_search_pagination() -> None:
    payload = {"total": 10, "offset": 0, "next": 2, "data": [S2_NORMAL_PAPER, S2_CONFERENCE_PAPER]}
    provider = SemanticScholarProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="x", page_size=2))
    assert len(page.items) == 2
    assert page.next_cursor == "2"
    assert page.total_estimated == 10


async def test_semantic_scholar_get_by_doi_not_found() -> None:
    provider = SemanticScholarProvider(_mock_client(_json_handler({}, status=404)))
    assert await provider.get_by_doi("10.1000/missing") is None


async def test_semantic_scholar_search_empty_results() -> None:
    payload: dict[str, Any] = {"total": 0, "offset": 0, "next": None, "data": []}
    provider = SemanticScholarProvider(_mock_client(_json_handler(payload)))
    page = await provider.search(SearchRequest(query="nothing"))
    assert page.items == []
    assert page.next_cursor is None


async def test_semantic_scholar_get_references() -> None:
    payload = {"data": [{"citedPaper": S2_NORMAL_PAPER}, {"citedPaper": None}]}
    provider = SemanticScholarProvider(_mock_client(_json_handler(payload)))
    refs = await provider.get_references("abc123")
    assert len(refs) == 1
    assert refs[0].provider_id == "abc123"


async def test_semantic_scholar_provider_error_normalized() -> None:
    provider = SemanticScholarProvider(_mock_client(_json_handler({}, status=500)))
    with pytest.raises(ProviderResponseError):
        await provider.get_by_doi("10.1000/x")

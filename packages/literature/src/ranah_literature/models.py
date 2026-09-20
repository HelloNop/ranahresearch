"""Provider-neutral literature models.

ProviderWork represents a Crossref/OpenAlex/Semantic Scholar record without
losing raw/provider metadata. It is never the canonical domain WorkRecord
(that mapping is EPIC-010) and never a `Citation` object (see
docs/DATA_MODEL.md #97 and docs/OPENDRAFT_ADOPTION.md #15).
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ProviderIdentifierType(StrEnum):
    DOI = "DOI"
    OPENALEX_ID = "OPENALEX_ID"
    SEMANTIC_SCHOLAR_ID = "SEMANTIC_SCHOLAR_ID"
    PMID = "PMID"
    PMCID = "PMCID"
    ARXIV_ID = "ARXIV_ID"


class ProviderIdentifier(BaseModel):
    identifier_type: ProviderIdentifierType
    identifier: str
    url: str | None = None


class ProviderAuthor(BaseModel):
    display_name: str
    given_name: str | None = None
    family_name: str | None = None
    orcid: str | None = None


class ProviderWork(BaseModel):
    provider: str
    provider_id: str
    doi: str | None = None
    title: str
    abstract: str | None = None
    authors: list[ProviderAuthor] = Field(default_factory=list)
    publication_year: int | None = None
    publication_date: str | None = None  # ISO 8601 date string; providers vary in precision.
    venue: str | None = None
    publisher: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    url: str | None = None
    work_type: str | None = None
    citation_count: int | None = None
    identifiers: list[ProviderIdentifier] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    cursor: str | None = None
    page_size: int = 25


class SearchPage(BaseModel):
    items: list[ProviderWork]
    next_cursor: str | None = None
    total_estimated: int | None = None


class ProviderCapability(BaseModel):
    can_get_references: bool = False
    can_get_citations: bool = False

"""Identifier/title normalization and canonical-work merge policy (EPIC-010)."""

import re
from dataclasses import dataclass, field
from typing import Any

from ranah_literature.models import ProviderAuthor, ProviderWork

_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


def normalize_doi(doi: str) -> str:
    """Canonical DOI form: trimmed, lowercased, URL/`doi:` prefix stripped.

    Raises ValueError for a value that normalizes to nothing (e.g. "", "  ",
    "doi:") - callers keep the original raw observation separately; this
    function only produces the canonical comparison key.
    """
    value = doi.strip().lower()
    for prefix in _DOI_URL_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    value = value.strip()
    if not value:
        raise ValueError(f"not a valid DOI: {doi!r}")
    return value


_TITLE_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_TITLE_WHITESPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercased, punctuation-stripped, whitespace-collapsed: good enough for exact-title
    matching. Fuzzy matching (EPIC-011) needs more than this."""
    value = _TITLE_PUNCTUATION.sub(" ", title.lower())
    return _TITLE_WHITESPACE.sub(" ", value).strip()


def split_display_name(name: str) -> tuple[str | None, str | None]:
    """Best-effort given/family split for providers (Semantic Scholar) that only
    report a single display name. The last token is treated as the family name;
    this is a heuristic, not a reliable name-parsing algorithm."""
    parts = name.strip().split()
    if not parts:
        return None, None
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


@dataclass(frozen=True, slots=True)
class FieldObservation:
    """One provider's reported value for one field. Never overwritten, only appended."""

    provider: str
    field_name: str
    value: object


@dataclass(slots=True)
class CanonicalWorkCandidate:
    """The result of merging one or more ProviderWork records believed to be the same
    publication. Not itself a WorkRecord: persistence is a separate, explicit step
    (see persistence.py) so this stays a pure, DB-free data structure."""

    doi: str | None
    title: str
    abstract: str | None
    authors: list[ProviderAuthor]
    publication_year: int | None
    publication_date: str | None
    venue: str | None
    publisher: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    url: str | None
    work_type: str | None
    source_works: list[ProviderWork] = field(default_factory=list)
    observations: list[FieldObservation] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def merge_provider_works(works: list[ProviderWork]) -> CanonicalWorkCandidate:
    """Deterministic field-level merge policy for ProviderWork records believed to
    refer to the same publication (docs/DATA_MODEL.md #89/#97). This function does
    not decide *which* works are the same publication - that is deduplication.py's
    job; here every input is assumed to already be one group.

    Field resolution:
    - doi: the first normalized non-empty DOI, in input order.
    - title: the longest non-empty title (a crude "most complete" proxy).
    - abstract: the longest non-empty abstract; abstracts are never concatenated.
    - authors: the full author list from whichever source reported the most authors.
    - everything else (year/date/venue/publisher/volume/issue/pages/url/type):
      first non-empty value, in input order.

    Every value seen (not just the chosen one) becomes a FieldObservation, and any
    field where sources disagree is listed in `conflicts` - resolution never hides
    a disagreement, it just picks a canonical display value.
    """
    if not works:
        raise ValueError("merge_provider_works requires at least one ProviderWork")

    observations: list[FieldObservation] = []
    conflicts: set[str] = set()

    doi: str | None = None
    doi_values: set[str] = set()
    for work in works:
        if not work.doi:
            continue
        try:
            normalized = normalize_doi(work.doi)
        except ValueError:
            continue
        observations.append(FieldObservation(work.provider, "doi", normalized))
        doi_values.add(normalized)
        if doi is None:
            doi = normalized
    if len(doi_values) > 1:
        conflicts.add("doi")

    for work in works:
        observations.append(FieldObservation(work.provider, "title", work.title))
    titles_with_text = [w for w in works if w.title]
    title = (
        max(titles_with_text, key=lambda w: len(w.title)).title
        if titles_with_text
        else works[0].title
    )
    if len({normalize_title(w.title) for w in titles_with_text}) > 1:
        conflicts.add("title")

    abstracts = [w for w in works if w.abstract]
    for work in abstracts:
        observations.append(FieldObservation(work.provider, "abstract", work.abstract))
    abstract = max(abstracts, key=lambda w: len(w.abstract or "")).abstract if abstracts else None

    authors_source = max(works, key=lambda w: len(w.authors))
    for work in works:
        if work.authors:
            observations.append(
                FieldObservation(work.provider, "authors", [a.display_name for a in work.authors])
            )
    authors = authors_source.authors

    def pick_first_non_empty(field_name: str) -> Any:
        chosen: Any = None
        seen: set[Any] = set()
        for work in works:
            value = getattr(work, field_name)
            if value in (None, ""):
                continue
            observations.append(FieldObservation(work.provider, field_name, value))
            seen.add(value)
            if chosen is None:
                chosen = value
        if len(seen) > 1:
            conflicts.add(field_name)
        return chosen

    return CanonicalWorkCandidate(
        doi=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        publication_year=pick_first_non_empty("publication_year"),
        publication_date=pick_first_non_empty("publication_date"),
        venue=pick_first_non_empty("venue"),
        publisher=pick_first_non_empty("publisher"),
        volume=pick_first_non_empty("volume"),
        issue=pick_first_non_empty("issue"),
        pages=pick_first_non_empty("pages"),
        url=pick_first_non_empty("url"),
        work_type=pick_first_non_empty("work_type"),
        source_works=works,
        observations=observations,
        conflicts=sorted(conflicts),
    )

"""EPIC-010 acceptance tests: DOI/title normalization and the canonical merge policy."""

import pytest
from ranah_literature.models import ProviderAuthor, ProviderWork
from ranah_literature.normalization import (
    merge_provider_works,
    normalize_doi,
    normalize_title,
    split_display_name,
)

# --- DOI normalization -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1000/xyz123", "10.1000/xyz123"),
        ("https://doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("http://doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("https://dx.doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("http://dx.doi.org/10.1000/xyz123", "10.1000/xyz123"),
        ("doi:10.1000/xyz123", "10.1000/xyz123"),
        ("  10.1000/XYZ123  ", "10.1000/xyz123"),
        ("10.1000/XyZ123", "10.1000/xyz123"),
    ],
)
def test_normalize_doi_handles_common_forms(raw: str, expected: str) -> None:
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "doi:", "https://doi.org/"])
def test_normalize_doi_rejects_empty_values(raw: str) -> None:
    with pytest.raises(ValueError, match="not a valid DOI"):
        normalize_doi(raw)


# --- Title normalization ------------------------------------------------------


def test_normalize_title_lowercases_and_strips_punctuation() -> None:
    assert normalize_title("Deep Learning: A Review!") == "deep learning a review"


def test_normalize_title_collapses_whitespace() -> None:
    assert normalize_title("Deep   Learning\n\tReview") == "deep learning review"


def test_normalize_title_does_not_mutate_display_title() -> None:
    # normalize_title returns a separate matching key; canonical display titles
    # are never rewritten in place (EPIC-010 #7).
    title = "Deep Learning: A Review!"
    normalize_title(title)
    assert title == "Deep Learning: A Review!"


# --- Author display-name splitting --------------------------------------------


def test_split_display_name_given_and_family() -> None:
    assert split_display_name("Jane Doe") == ("Jane", "Doe")


def test_split_display_name_multiple_given_names() -> None:
    assert split_display_name("Jane A. Doe") == ("Jane A.", "Doe")


def test_split_display_name_single_token() -> None:
    assert split_display_name("Cher") == (None, "Cher")


def test_split_display_name_empty() -> None:
    assert split_display_name("   ") == (None, None)


# --- Canonical merge policy ----------------------------------------------------


def _work(**overrides: object) -> ProviderWork:
    defaults: dict[str, object] = {
        "provider": "crossref",
        "provider_id": "10.1/abc",
        "doi": "10.1/abc",
        "title": "A study of things",
    }
    defaults.update(overrides)
    return ProviderWork(**defaults)  # type: ignore[arg-type]


def test_merge_requires_at_least_one_work() -> None:
    with pytest.raises(ValueError):
        merge_provider_works([])


def test_merge_prefers_longest_title_and_abstract() -> None:
    a = _work(provider="crossref", title="A study", abstract="Short.")
    b = _work(
        provider="openalex",
        title="A study of things in detail",
        abstract="A much longer abstract text.",
    )
    candidate = merge_provider_works([a, b])
    assert candidate.title == "A study of things in detail"
    assert candidate.abstract == "A much longer abstract text."


def test_merge_never_concatenates_abstracts() -> None:
    a = _work(provider="crossref", abstract="Abstract one.")
    b = _work(provider="openalex", abstract="Abstract two, which happens to be longer overall.")
    candidate = merge_provider_works([a, b])
    # The richest single abstract wins; the two are never joined into one string.
    assert candidate.abstract == "Abstract two, which happens to be longer overall."


def test_merge_preserves_full_author_list_not_just_surname() -> None:
    authors = [
        ProviderAuthor(
            display_name="Jane Doe", given_name="Jane", family_name="Doe", orcid="0000-0001"
        ),
        ProviderAuthor(display_name="John Smith", given_name="John", family_name="Smith"),
    ]
    a = _work(provider="crossref", authors=authors)
    b = _work(provider="openalex", authors=[])
    candidate = merge_provider_works([a, b])
    assert candidate.authors == authors
    assert candidate.authors[0].orcid == "0000-0001"


def test_merge_flags_conflicting_publication_year_without_hiding_it() -> None:
    a = _work(provider="crossref", publication_year=2024)
    b = _work(provider="openalex", publication_year=2023)
    candidate = merge_provider_works([a, b])
    assert candidate.publication_year in (2023, 2024)
    assert "publication_year" in candidate.conflicts


def test_merge_records_every_provider_observation() -> None:
    a = _work(provider="crossref", publication_year=2024)
    b = _work(provider="openalex", publication_year=2024)
    candidate = merge_provider_works([a, b])
    year_observations = [o for o in candidate.observations if o.field_name == "publication_year"]
    assert {o.provider for o in year_observations} == {"crossref", "openalex"}
    assert "publication_year" not in candidate.conflicts  # both agree


def test_merge_single_work_is_a_no_op_pass_through() -> None:
    a = _work(provider="crossref", title="Solo work")
    candidate = merge_provider_works([a])
    assert candidate.title == "Solo work"
    assert candidate.conflicts == []
    assert candidate.source_works == [a]

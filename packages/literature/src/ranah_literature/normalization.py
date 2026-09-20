"""Identifier/title normalization. Foundation for EPIC-010 normalization and EPIC-011 dedupe."""

import re


def normalize_doi(doi: str) -> str:
    """Strips URL prefixes/whitespace and lowercases, so the same DOI compares equal
    regardless of how a provider formatted it."""
    value = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value


_TITLE_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_TITLE_WHITESPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercased, punctuation-stripped, whitespace-collapsed: good enough for exact-title
    matching. Fuzzy matching (EPIC-011) needs more than this."""
    value = _TITLE_PUNCTUATION.sub(" ", title.lower())
    return _TITLE_WHITESPACE.sub(" ", value).strip()

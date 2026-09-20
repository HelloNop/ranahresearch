"""Publication-record deduplication (EPIC-011).

This is record dedup (same publication), not Study linking (EPIC-028): a
conference abstract, its main-article version, and a follow-up publication
may belong to the same underlying Study but are not bibliographic duplicates
and stay as separate WorkRecords here (docs/OPENDRAFT_ADOPTION.md #14).

Staged, deterministic matching (docs/OPENDRAFT_ADOPTION.md #13):
A. exact normalized DOI
B. exact external identifier
C. exact normalized title
D. blocking (year + first author + title prefix) to avoid O(n^2) comparisons
E. fuzzy title similarity, only within a block
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum

from ranah_domain.enums import DuplicateDecisionType

from ranah_literature.normalization import normalize_doi, normalize_title


class MatchTier(StrEnum):
    EXACT = "EXACT"
    HIGH_CONFIDENCE_DUPLICATE = "HIGH_CONFIDENCE_DUPLICATE"
    POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"
    NOT_DUPLICATE = "NOT_DUPLICATE"


@dataclass(frozen=True, slots=True)
class DedupThresholds:
    """Explicit and configurable - never buried inside the matching algorithm."""

    high_confidence_title_similarity: float = 0.92
    potential_duplicate_title_similarity: float = 0.80
    title_prefix_block_length: int = 20


DEFAULT_THRESHOLDS = DedupThresholds()


@dataclass(frozen=True, slots=True)
class DedupCandidate:
    """The minimal shape deduplication needs. Callers adapt real WorkRecord rows
    into this; this module has no ORM/DB dependency of its own."""

    work_id: str
    doi: str | None = None
    title: str = ""
    publication_year: int | None = None
    first_author_family: str | None = None
    external_ids: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    work_id_a: str
    work_id_b: str
    tier: MatchTier
    score: float | None
    signals: dict[str, object] = field(default_factory=dict)


def decision_for_tier(tier: MatchTier) -> DuplicateDecisionType:
    """Conservative by default: only an EXACT signal (DOI or external ID) is safe
    to auto-merge. Everything else needs a human. False merges are scientifically
    dangerous (docs/IMPLEMENTATION_ROADMAP.md EPIC-011)."""
    if tier == MatchTier.EXACT:
        return DuplicateDecisionType.MERGE
    if tier == MatchTier.NOT_DUPLICATE:
        return DuplicateDecisionType.KEEP_SEPARATE
    return DuplicateDecisionType.REVIEW_REQUIRED


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_duplicate_matches(
    candidates: list[DedupCandidate], thresholds: DedupThresholds = DEFAULT_THRESHOLDS
) -> list[DuplicateMatch]:
    matches: list[DuplicateMatch] = []
    matched_pairs: set[frozenset[str]] = set()

    def record(
        a: DedupCandidate,
        b: DedupCandidate,
        tier: MatchTier,
        score: float | None,
        signals: dict[str, object],
    ) -> None:
        if a.work_id == b.work_id:
            return  # never match a candidate against itself
        key = frozenset((a.work_id, b.work_id))
        if key in matched_pairs:
            return
        matched_pairs.add(key)
        matches.append(
            DuplicateMatch(
                work_id_a=a.work_id, work_id_b=b.work_id, tier=tier, score=score, signals=signals
            )
        )

    # Stage A: exact normalized DOI - the strongest possible match.
    by_doi: dict[str, list[DedupCandidate]] = {}
    for c in candidates:
        if not c.doi:
            continue
        try:
            key = normalize_doi(c.doi)
        except ValueError:
            continue
        by_doi.setdefault(key, []).append(c)
    for group in by_doi.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                record(group[i], group[j], MatchTier.EXACT, 1.0, {"signal": "exact_doi"})

    # Stage B: exact external identifier (e.g. same OpenAlex ID).
    by_identifier: dict[tuple[str, str], list[DedupCandidate]] = {}
    for c in candidates:
        for identifier in c.external_ids:
            by_identifier.setdefault(identifier, []).append(c)
    for group in by_identifier.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                record(group[i], group[j], MatchTier.EXACT, 1.0, {"signal": "exact_external_id"})

    # Stage C: exact normalized title. Flags a conflicting DOI rather than hiding it.
    by_title: dict[str, list[DedupCandidate]] = {}
    for c in candidates:
        if not c.title:
            continue
        by_title.setdefault(normalize_title(c.title), []).append(c)
    for group in by_title.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                signals: dict[str, object] = {"signal": "exact_title"}
                if a.doi and b.doi:
                    try:
                        if normalize_doi(a.doi) != normalize_doi(b.doi):
                            signals["conflicting_doi"] = True
                    except ValueError:
                        pass
                record(a, b, MatchTier.HIGH_CONFIDENCE_DUPLICATE, 1.0, signals)

    # Stage D: blocking. Only candidates sharing a block key are ever compared,
    # instead of scanning every pair in the corpus.
    blocks: dict[tuple[object, str, str], list[DedupCandidate]] = {}
    for c in candidates:
        if not c.title:
            continue
        block_key = (
            c.publication_year,
            (c.first_author_family or "").lower(),
            normalize_title(c.title)[: thresholds.title_prefix_block_length],
        )
        blocks.setdefault(block_key, []).append(c)

    # Stage E: deterministic fuzzy similarity, only within a block.
    for group in blocks.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                score = _title_similarity(normalize_title(a.title), normalize_title(b.title))
                if score >= thresholds.high_confidence_title_similarity:
                    tier = MatchTier.HIGH_CONFIDENCE_DUPLICATE
                elif score >= thresholds.potential_duplicate_title_similarity:
                    tier = MatchTier.POTENTIAL_DUPLICATE
                else:
                    continue
                record(
                    a,
                    b,
                    tier,
                    score,
                    {
                        "signal": "fuzzy_title",
                        "year_match": a.publication_year == b.publication_year,
                    },
                )

    return matches

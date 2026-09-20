"""EPIC-011 acceptance tests: staged matching, thresholds, and conservative decisions.

Golden fixtures A-E come directly from the EPIC-011 spec.
"""

from ranah_domain.enums import DuplicateDecisionType
from ranah_literature.deduplication import (
    DedupCandidate,
    DedupThresholds,
    MatchTier,
    decision_for_tier,
    find_duplicate_matches,
)


def test_decision_for_tier_is_conservative_by_default() -> None:
    assert decision_for_tier(MatchTier.EXACT) == DuplicateDecisionType.MERGE
    assert (
        decision_for_tier(MatchTier.HIGH_CONFIDENCE_DUPLICATE)
        == DuplicateDecisionType.REVIEW_REQUIRED
    )
    assert decision_for_tier(MatchTier.POTENTIAL_DUPLICATE) == DuplicateDecisionType.REVIEW_REQUIRED
    assert decision_for_tier(MatchTier.NOT_DUPLICATE) == DuplicateDecisionType.KEEP_SEPARATE


def test_golden_a_same_doi_is_exact_merge_candidate() -> None:
    a = DedupCandidate(work_id="1", doi="10.1/x", title="A study of things", publication_year=2020)
    b = DedupCandidate(
        work_id="2",
        doi="https://doi.org/10.1/X",
        title="A totally different title",
        publication_year=2020,
    )
    matches = find_duplicate_matches([a, b])
    assert len(matches) == 1
    assert matches[0].tier == MatchTier.EXACT
    assert decision_for_tier(matches[0].tier) == DuplicateDecisionType.MERGE


def test_golden_b_same_title_year_author_missing_doi_is_duplicate_candidate() -> None:
    a = DedupCandidate(
        work_id="1",
        doi=None,
        title="Generative AI in higher education",
        publication_year=2023,
        first_author_family="Doe",
    )
    b = DedupCandidate(
        work_id="2",
        doi=None,
        title="Generative AI in higher education",
        publication_year=2023,
        first_author_family="Doe",
    )
    matches = find_duplicate_matches([a, b])
    assert len(matches) == 1
    assert matches[0].tier == MatchTier.HIGH_CONFIDENCE_DUPLICATE
    assert decision_for_tier(matches[0].tier) == DuplicateDecisionType.REVIEW_REQUIRED


def test_golden_c_similar_titles_different_study_kept_separate() -> None:
    a = DedupCandidate(
        work_id="1",
        title="Machine learning for climate prediction",
        publication_year=2021,
        first_author_family="Lee",
    )
    b = DedupCandidate(
        work_id="2",
        title="Machine learning for crop yield estimation",
        publication_year=2021,
        first_author_family="Lee",
    )
    matches = find_duplicate_matches([a, b])
    # Below the potential-duplicate threshold: never flagged, i.e. effectively kept separate.
    assert matches == []


def test_golden_d_same_title_conflicting_doi_is_review_required() -> None:
    a = DedupCandidate(
        work_id="1", doi="10.1/aaa", title="A study of things", publication_year=2022
    )
    b = DedupCandidate(
        work_id="2", doi="10.1/bbb", title="A study of things", publication_year=2022
    )
    matches = find_duplicate_matches([a, b])
    assert len(matches) == 1
    assert matches[0].tier == MatchTier.HIGH_CONFIDENCE_DUPLICATE
    assert matches[0].signals.get("conflicting_doi") is True
    assert decision_for_tier(matches[0].tier) == DuplicateDecisionType.REVIEW_REQUIRED


def test_golden_e_conference_abstract_vs_journal_article_not_auto_deduped() -> None:
    # Same underlying study, different publication type - topic/title similarity
    # alone must not merge them; this is Study linking's job (EPIC-028), not ours.
    conference = DedupCandidate(
        work_id="1",
        title="Effects of X on Y: preliminary results",
        publication_year=2020,
        first_author_family="Kim",
    )
    journal = DedupCandidate(
        work_id="2",
        title="Effects of X on Y: a randomized controlled trial",
        publication_year=2021,
        first_author_family="Kim",
    )
    matches = find_duplicate_matches([conference, journal])
    # Different publication years break the blocking key entirely, and the titles
    # are not an exact match either - never auto-merged as if they were duplicates.
    assert matches == []


def test_exact_external_identifier_match_is_exact_tier() -> None:
    a = DedupCandidate(work_id="1", title="X", external_ids=(("openalex", "W123"),))
    b = DedupCandidate(work_id="2", title="Y", external_ids=(("openalex", "W123"),))
    matches = find_duplicate_matches([a, b])
    assert len(matches) == 1
    assert matches[0].tier == MatchTier.EXACT
    assert matches[0].signals["signal"] == "exact_external_id"


def test_no_unrestricted_pairwise_scan_large_corpus_stays_fast() -> None:
    # 500 distinct candidates spread across many blocks; this must not attempt a
    # full O(n^2) comparison. Loose bound: comfortably fast well under a second.
    import time

    candidates = [
        DedupCandidate(
            work_id=str(i),
            title=f"Unique study number {i} about topic {i % 50}",
            publication_year=2000 + (i % 20),
            first_author_family=f"Author{i % 100}",
        )
        for i in range(500)
    ]
    start = time.monotonic()
    matches = find_duplicate_matches(candidates)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0
    assert isinstance(matches, list)


def test_thresholds_are_configurable_not_buried_in_algorithm() -> None:
    a = DedupCandidate(
        work_id="1",
        title="Somewhat similar title alpha",
        publication_year=2020,
        first_author_family="X",
    )
    b = DedupCandidate(
        work_id="2",
        title="Somewhat similar title beta",
        publication_year=2020,
        first_author_family="X",
    )

    strict = DedupThresholds(
        potential_duplicate_title_similarity=0.99, high_confidence_title_similarity=0.999
    )
    assert find_duplicate_matches([a, b], strict) == []

    lenient = DedupThresholds(
        potential_duplicate_title_similarity=0.5, high_confidence_title_similarity=0.99
    )
    matches = find_duplicate_matches([a, b], lenient)
    assert len(matches) == 1
    assert matches[0].tier == MatchTier.POTENTIAL_DUPLICATE


def test_no_destructive_action_matches_are_pure_data() -> None:
    # find_duplicate_matches never mutates or removes candidates - it only reports.
    candidates = [
        DedupCandidate(work_id="1", doi="10.1/a", title="t"),
        DedupCandidate(work_id="2", doi="10.1/a", title="t"),
    ]
    snapshot = list(candidates)
    find_duplicate_matches(candidates)
    assert candidates == snapshot

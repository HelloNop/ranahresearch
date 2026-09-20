"""EPIC-012 acceptance tests: identity verification, never eligibility.

Critical rule under test: "confirmed only by Crossref" must become
PARTIALLY_VERIFIED, never EXCLUDED - and a provider outage must be
distinguishable from "this DOI genuinely doesn't exist anywhere".
"""

from ranah_domain.enums import WorkVerificationStatus, WorkVerificationType
from ranah_literature.errors import ProviderResponseError
from ranah_literature.models import ProviderWork
from ranah_literature.providers.fake import FakeAcademicProvider
from ranah_literature.verification import SourceVerificationService

DOI = "10.1/x"


class _FlakyProvider(FakeAcademicProvider):
    """A provider that always fails, standing in for a temporary outage."""

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        raise ProviderResponseError("upstream 503")


def _reference(doi: str = DOI) -> ProviderWork:
    return ProviderWork(
        provider="crossref", provider_id=doi, doi=doi, title="A study", publication_year=2022
    )


async def test_confirmed_by_three_sources_is_verified() -> None:
    ref = _reference()
    providers = [
        FakeAcademicProvider([ref], name=p) for p in ("crossref", "openalex", "semantic_scholar")
    ]
    service = SourceVerificationService(providers)
    outcome = await service.verify_by_doi(DOI, ref)
    assert outcome.status == WorkVerificationStatus.VERIFIED
    assert set(outcome.confirmed_by) == {"crossref", "openalex", "semantic_scholar"}


async def test_confirmed_by_two_sources_is_verified() -> None:
    ref = _reference()
    providers = [
        FakeAcademicProvider([ref], name="crossref"),
        FakeAcademicProvider([ref], name="openalex"),
        FakeAcademicProvider([], name="semantic_scholar"),
    ]
    service = SourceVerificationService(providers)
    outcome = await service.verify_by_doi(DOI, ref)
    assert outcome.status == WorkVerificationStatus.VERIFIED
    assert len(outcome.confirmed_by) == 2


async def test_confirmed_by_single_source_is_partially_verified_not_excluded() -> None:
    """The mandatory boundary: single-source confirmation is retained, never excluded."""
    ref = _reference()
    providers = [
        FakeAcademicProvider([ref], name="crossref"),
        FakeAcademicProvider([], name="openalex"),
        FakeAcademicProvider([], name="semantic_scholar"),
    ]
    service = SourceVerificationService(providers)
    outcome = await service.verify_by_doi(DOI, ref)
    assert outcome.status == WorkVerificationStatus.PARTIALLY_VERIFIED
    assert outcome.confirmed_by == ["crossref"]


async def test_metadata_conflict_is_detected_and_persisted_as_conflict_status() -> None:
    ref = _reference()
    conflicting = ref.model_copy(update={"title": "A completely different study"})
    service = SourceVerificationService([FakeAcademicProvider([conflicting])])
    outcome = await service.verify_by_doi(DOI, ref)
    assert outcome.status == WorkVerificationStatus.CONFLICT
    assert outcome.conflicts[0]["issues"] == ["title_mismatch"]


async def test_doi_not_found_anywhere_is_unverified_not_failed() -> None:
    service = SourceVerificationService([FakeAcademicProvider([]), FakeAcademicProvider([])])
    outcome = await service.verify_by_doi("10.1/nowhere", _reference("10.1/nowhere"))
    assert outcome.status == WorkVerificationStatus.UNVERIFIED
    assert outcome.confirmed_by == []


async def test_provider_outage_distinguished_from_scientific_identity_failure() -> None:
    ref = _reference()
    service = SourceVerificationService(
        [_FlakyProvider([], name="flaky"), FakeAcademicProvider([ref], name="crossref")]
    )
    outcome = await service.verify_by_doi(DOI, ref)
    assert len(outcome.outages) == 1
    assert outcome.outages[0].provider == "flaky"
    # One real provider still confirmed it - not a FAILED verification.
    assert outcome.status == WorkVerificationStatus.PARTIALLY_VERIFIED


async def test_all_providers_unreachable_is_failed_not_unverified() -> None:
    ref = _reference()
    service = SourceVerificationService(
        [_FlakyProvider([], name="flaky-1"), _FlakyProvider([], name="flaky-2")]
    )
    outcome = await service.verify_by_doi(DOI, ref)
    assert outcome.status == WorkVerificationStatus.FAILED
    assert len(outcome.outages) == 2


async def test_verification_type_is_doi_identity() -> None:
    ref = _reference()
    service = SourceVerificationService([FakeAcademicProvider([ref])])
    outcome = await service.verify_by_doi(DOI, ref)
    assert outcome.verification_type == WorkVerificationType.DOI_IDENTITY

"""Source identity verification (EPIC-012).

Identity confidence only - never eligibility, never a screening decision.
"Confirmed only by Crossref" must never become EXCLUDED; it becomes
PARTIALLY_VERIFIED. Screening/inclusion happens later using protocol
criteria (docs/OPENDRAFT_ADOPTION.md #11, #21; docs/DATA_MODEL.md #27).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from ranah_domain.enums import WorkVerificationStatus, WorkVerificationType

from ranah_literature.errors import ProviderError
from ranah_literature.models import ProviderWork
from ranah_literature.normalization import normalize_doi, normalize_title
from ranah_literature.providers.base import AcademicProvider


@dataclass(frozen=True, slots=True)
class ProviderOutage:
    """A provider we could not reach - distinct from a provider that simply doesn't
    have this DOI. FAILED status is reserved for when every provider is unreachable,
    never for "not confirmed by all providers" (docs #21)."""

    provider: str
    reason: str


@dataclass(slots=True)
class VerificationOutcome:
    verification_type: WorkVerificationType
    status: WorkVerificationStatus
    confirmed_by: list[str] = field(default_factory=list)
    conflicts: list[dict[str, object]] = field(default_factory=list)
    outages: list[ProviderOutage] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)


def _compare(reference: ProviderWork, found: ProviderWork, target_doi: str) -> list[str]:
    issues: list[str] = []
    if found.doi:
        try:
            if normalize_doi(found.doi) != target_doi:
                issues.append("doi_mismatch")
        except ValueError:
            issues.append("doi_mismatch")
    if (
        reference.title
        and found.title
        and normalize_title(reference.title) != normalize_title(found.title)
    ):
        issues.append("title_mismatch")
    if (
        reference.publication_year
        and found.publication_year
        and reference.publication_year != found.publication_year
    ):
        issues.append("year_mismatch")
    return issues


def _status_for(
    confirmed_by: list[str],
    conflicts: list[dict[str, object]],
    outages: list[ProviderOutage],
    providers_queried: int,
) -> WorkVerificationStatus:
    if conflicts:
        return WorkVerificationStatus.CONFLICT
    if not confirmed_by and outages and len(outages) == providers_queried:
        return WorkVerificationStatus.FAILED
    if len(confirmed_by) >= 2:
        return WorkVerificationStatus.VERIFIED
    if len(confirmed_by) == 1:
        return WorkVerificationStatus.PARTIALLY_VERIFIED
    return WorkVerificationStatus.UNVERIFIED


class SourceVerificationService:
    """Determines source identity and metadata confidence. Not scientific
    relevance, not screening, not inclusion eligibility (docs #12 header)."""

    def __init__(self, providers: Sequence[AcademicProvider]) -> None:
        self._providers = providers

    async def verify_by_doi(self, doi: str, reference: ProviderWork) -> VerificationOutcome:
        """Looks the DOI up across every configured provider and compares reported
        metadata against `reference` (the canonical candidate)."""
        confirmed_by: list[str] = []
        conflicts: list[dict[str, object]] = []
        outages: list[ProviderOutage] = []
        target_doi = normalize_doi(doi)

        for provider in self._providers:
            try:
                found = await provider.get_by_doi(doi)
            except ProviderError as exc:
                outages.append(ProviderOutage(provider=provider.name, reason=str(exc)))
                continue
            if found is None:
                continue
            issues = _compare(reference, found, target_doi)
            if issues:
                conflicts.append({"provider": provider.name, "issues": issues})
            else:
                confirmed_by.append(provider.name)

        status = _status_for(confirmed_by, conflicts, outages, len(self._providers))
        return VerificationOutcome(
            verification_type=WorkVerificationType.DOI_IDENTITY,
            status=status,
            confirmed_by=confirmed_by,
            conflicts=conflicts,
            outages=outages,
            details={"target_doi": target_doi, "providers_queried": len(self._providers)},
        )

"""Literature discovery orchestration: the integration point for EPIC-009 through
EPIC-012 (docs/IMPLEMENTATION_ROADMAP.md EPIC-017's "24. Literature Discovery
Service Integration").

    SearchQuery -> provider.search() -> SearchRun/SearchResult
                -> ProviderWork -> normalization -> WorkRecord
                -> deduplication -> DuplicateGroup/Decision
                -> source verification -> WorkVerification

This is a plain async service, not a Temporal workflow: EPIC-017 can wrap it in
an Activity later. Each stage below is independently testable (normalization,
deduplication, verification have no DB dependency of their own); this module
only coordinates them and must not hide decisions inside one giant method.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ranah_domain.enums import SearchRunStatus
from ranah_domain.repositories import search as search_repo
from ranah_domain.schemas.search import SearchResultCreate, SearchRunCreate
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_literature.deduplication import DedupCandidate, find_duplicate_matches
from ranah_literature.errors import ProviderError
from ranah_literature.models import ProviderWork, SearchRequest
from ranah_literature.normalization import merge_provider_works, normalize_doi
from ranah_literature.persistence import (
    persist_canonical_work,
    persist_duplicate_match,
    persist_verification,
)
from ranah_literature.providers.base import AcademicProvider
from ranah_literature.verification import SourceVerificationService


@dataclass(slots=True)
class ProviderSearchOutcome:
    provider: str
    retrieved: int
    reported: int | None
    error: str | None = None


@dataclass(slots=True)
class DiscoveryReport:
    provider_outcomes: list[ProviderSearchOutcome] = field(default_factory=list)
    work_ids: list[uuid.UUID] = field(default_factory=list)
    duplicate_group_count: int = 0
    verification_status_counts: dict[str, int] = field(default_factory=dict)


def _group_by_likely_same_publication(works: list[ProviderWork]) -> list[list[ProviderWork]]:
    """DOI is the strongest signal, so works sharing a normalized DOI are grouped
    before persistence (this is what EPIC-010 means by normalization "identifying
    likely same publication"). Works without a usable DOI are left as singletons;
    EPIC-011's staged dedup is what catches same-publication records that don't
    share a DOI, operating on the WorkRecords this function's groups produce."""
    by_doi: dict[str, list[ProviderWork]] = {}
    singles: list[list[ProviderWork]] = []
    for work in works:
        if work.doi:
            try:
                key = normalize_doi(work.doi)
            except ValueError:
                singles.append([work])
                continue
            by_doi.setdefault(key, []).append(work)
        else:
            singles.append([work])
    return list(by_doi.values()) + singles


class LiteratureDiscoveryService:
    def __init__(
        self,
        session: AsyncSession,
        providers: Mapping[str, AcademicProvider],
        *,
        verification_providers: Sequence[AcademicProvider] | None = None,
    ) -> None:
        self._session = session
        self._providers = providers
        self._verification = SourceVerificationService(
            verification_providers or list(providers.values())
        )

    async def run(
        self, project_id: uuid.UUID, search_query_id: uuid.UUID, request: SearchRequest
    ) -> DiscoveryReport:
        report = DiscoveryReport()
        provider_works = await self._search_all_providers(
            project_id, search_query_id, request, report
        )
        if not provider_works:
            return report

        candidates, work_ids_by_candidate_key = await self._normalize_and_persist(
            project_id, provider_works, report
        )
        await self._deduplicate(project_id, candidates, report)
        await self._verify(work_ids_by_candidate_key, report)
        return report

    async def _search_all_providers(
        self,
        project_id: uuid.UUID,
        search_query_id: uuid.UUID,
        request: SearchRequest,
        report: DiscoveryReport,
    ) -> list[ProviderWork]:
        provider_works: list[ProviderWork] = []
        for name, provider in self._providers.items():
            run = await search_repo.create_run(
                self._session,
                SearchRunCreate(
                    project_id=project_id,
                    search_query_id=search_query_id,
                    provider=name,
                    executed_query=request.query,
                    executed_filters=request.filters,
                ),
            )
            try:
                page = await provider.search(request)
            except ProviderError as exc:
                await search_repo.complete_run(
                    self._session,
                    run.id,
                    status=SearchRunStatus.FAILED,
                    provider_metadata={"error": str(exc)},
                )
                report.provider_outcomes.append(
                    ProviderSearchOutcome(provider=name, retrieved=0, reported=None, error=str(exc))
                )
                continue

            for rank, work in enumerate(page.items):
                await search_repo.add_result(
                    self._session,
                    SearchResultCreate(
                        search_run_id=run.id,
                        provider_record_id=work.provider_id,
                        rank=rank,
                        normalized_payload=work.model_dump(mode="json"),
                    ),
                )
            await search_repo.complete_run(
                self._session,
                run.id,
                status=SearchRunStatus.COMPLETED,
                result_count_reported=page.total_estimated,
                result_count_retrieved=len(page.items),
            )
            report.provider_outcomes.append(
                ProviderSearchOutcome(
                    provider=name, retrieved=len(page.items), reported=page.total_estimated
                )
            )
            provider_works.extend(page.items)
        return provider_works

    async def _normalize_and_persist(
        self, project_id: uuid.UUID, provider_works: list[ProviderWork], report: DiscoveryReport
    ) -> tuple[list[DedupCandidate], dict[str, ProviderWork]]:
        candidates: list[DedupCandidate] = []
        representative_work_by_id: dict[str, ProviderWork] = {}

        for group in _group_by_likely_same_publication(provider_works):
            candidate = merge_provider_works(group)
            record = await persist_canonical_work(self._session, project_id, candidate)
            report.work_ids.append(record.id)
            representative_work_by_id[str(record.id)] = group[0]
            candidates.append(
                DedupCandidate(
                    work_id=str(record.id),
                    doi=candidate.doi,
                    title=candidate.title,
                    publication_year=candidate.publication_year,
                    first_author_family=(
                        candidate.authors[0].family_name if candidate.authors else None
                    ),
                    external_ids=tuple(
                        {
                            (identifier.identifier_type.value, identifier.identifier)
                            for source in group
                            for identifier in source.identifiers
                        }
                    ),
                )
            )
        return candidates, representative_work_by_id

    async def _deduplicate(
        self, project_id: uuid.UUID, candidates: list[DedupCandidate], report: DiscoveryReport
    ) -> None:
        matches = find_duplicate_matches(candidates)
        for match in matches:
            await persist_duplicate_match(
                self._session,
                project_id,
                match,
                uuid.UUID(match.work_id_a),
                uuid.UUID(match.work_id_b),
            )
        report.duplicate_group_count = len(matches)

    async def _verify(
        self,
        representative_work_by_id: dict[str, ProviderWork],
        report: DiscoveryReport,
    ) -> None:
        for work_id_str, representative in representative_work_by_id.items():
            if not representative.doi:
                continue
            outcome = await self._verification.verify_by_doi(representative.doi, representative)
            await persist_verification(self._session, uuid.UUID(work_id_str), outcome)
            report.verification_status_counts[outcome.status.value] = (
                report.verification_status_counts.get(outcome.status.value, 0) + 1
            )

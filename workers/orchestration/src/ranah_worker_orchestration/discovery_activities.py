import os
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, cast

from ranah_domain.db import session_scope
from ranah_domain.enums import SearchRunStatus, WorkVerificationStatus, WorkVerificationType
from ranah_domain.models.project import ResearchProject
from ranah_domain.models.search import SearchQuery, SearchResult, SearchRun, SearchStrategy
from ranah_domain.models.work import WorkIdentifier, WorkRecord
from ranah_domain.models.workflow import WorkflowRun
from ranah_literature.deduplication import DedupCandidate, find_duplicate_matches
from ranah_literature.discovery import DiscoveryReport, LiteratureDiscoveryService
from ranah_literature.http import IntervalRateLimiter, ProviderHTTPClient
from ranah_literature.models import ProviderWork, SearchRequest
from ranah_literature.persistence import persist_duplicate_match, persist_verification
from ranah_literature.providers.base import AcademicProvider
from ranah_literature.providers.crossref import CrossrefProvider
from ranah_literature.providers.openalex import OpenAlexProvider
from ranah_literature.providers.semantic_scholar import SemanticScholarProvider
from ranah_literature.verification import SourceVerificationService, VerificationOutcome
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration.activities import _session_factory
from ranah_worker_orchestration.research_activities import event, finish_operation, operation


@lru_cache
def providers() -> dict[str, AcademicProvider]:
    # ponytail: quotas are per worker process; use shared quotas before scaling workers.
    return {
        "crossref": CrossrefProvider(
            ProviderHTTPClient(
                "https://api.crossref.org",
                rate_limit_hook=IntervalRateLimiter(1),
            )
        ),
        "openalex": OpenAlexProvider(
            ProviderHTTPClient(
                "https://api.openalex.org",
                rate_limit_hook=IntervalRateLimiter(1),
                params={"api_key": os.environ["OPENALEX_API_KEY"]}
                if os.environ.get("OPENALEX_API_KEY")
                else {},
            )
        ),
        "semantic_scholar": SemanticScholarProvider(
            ProviderHTTPClient(
                "https://api.semanticscholar.org/graph/v1",
                rate_limit_hook=IntervalRateLimiter(1),
                headers={"x-api-key": os.environ["SEMANTIC_SCHOLAR_API_KEY"]}
                if os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
                else {},
            )
        ),
    }


@activity.defn
async def validate_discovery(
    operation_id: str, project_id: str, strategy_id: str, query_ids: list[str]
) -> None:
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        strategy = await session.get(SearchStrategy, uuid.UUID(strategy_id))
        actual = list(
            await session.scalars(
                select(SearchQuery.id).where(
                    SearchQuery.search_strategy_id == uuid.UUID(strategy_id)
                )
            )
        )
        if (
            str(row.project_id) != project_id
            or not strategy
            or strategy.project_id != row.project_id
            or set(map(str, actual)) != set(query_ids)
            or not query_ids
        ):
            raise ApplicationError("Invalid discovery scope", non_retryable=True)
        if "search_started" not in row.details:
            row.details = {**row.details, "search_started": True}
            event(session, row.project_id, "SEARCH_STARTED", operation_id=operation_id)


def provider_filters(provider: str, filters: dict[str, Any]) -> dict[str, Any]:
    start, end = filters.get("year_from"), filters.get("year_to")
    if provider == "semantic_scholar":
        return {"year": f"{start or ''}-{end or ''}"} if start or end else {}
    keys = (
        ("from-pub-date", "until-pub-date")
        if provider == "crossref"
        else ("from_publication_date", "to_publication_date")
    )
    return {
        key: value
        for key, value in zip(
            keys,
            [f"{start}-01-01" if start else None, f"{end}-12-31" if end else None],
            strict=True,
        )
        if value is not None
    }


@activity.defn
async def execute_provider_search(operation_id: str, query_id: str) -> str:
    async with session_scope(_session_factory()) as session:
        row = await session.get(WorkflowRun, uuid.UUID(operation_id))
        query = await session.get(SearchQuery, uuid.UUID(query_id), with_for_update=True)
        assert row is not None and query is not None
        existing = await session.scalar(
            select(SearchRun).where(
                SearchRun.operation_id == row.id, SearchRun.search_query_id == query.id
            )
        )
        if existing is not None:
            return existing.status.value
        filters = provider_filters(query.provider, query.filters)
        page = await providers()[query.provider].search(
            SearchRequest(
                query=query.query_text,
                filters=filters,
                page_size=25,
            )
        )
        run = SearchRun(
            project_id=row.project_id,
            operation_id=row.id,
            search_query_id=query.id,
            provider=query.provider,
            executed_query=query.query_text,
            executed_filters=filters,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status=SearchRunStatus.PARTIAL if page.next_cursor else SearchRunStatus.COMPLETED,
            result_count_reported=page.total_estimated,
            result_count_retrieved=len({work.provider_id for work in page.items}),
            provider_metadata={
                "next_cursor": page.next_cursor,
                "limit": 25,
                "bounded_discovery": True,
            },
        )
        session.add(run)
        await session.flush()
        for rank, work in enumerate({w.provider_id: w for w in page.items}.values()):
            session.add(
                SearchResult(
                    search_run_id=run.id,
                    provider_record_id=work.provider_id,
                    rank=rank,
                    normalized_payload=work.model_dump(mode="json"),
                )
            )
        event(
            session,
            row.project_id,
            "PROVIDER_SEARCH_COMPLETED",
            operation_id=operation_id,
            provider=query.provider,
            status=run.status.value,
            retrieved=run.result_count_retrieved,
            bounded=bool(page.next_cursor),
        )
        return run.status.value


@activity.defn
async def record_provider_failure(operation_id: str, query_id: str, error: str) -> None:
    async with session_scope(_session_factory()) as session:
        row = await session.get(WorkflowRun, uuid.UUID(operation_id))
        query = await session.get(SearchQuery, uuid.UUID(query_id), with_for_update=True)
        assert row is not None and query is not None
        if await session.scalar(
            select(SearchRun.id).where(
                SearchRun.operation_id == row.id, SearchRun.search_query_id == query.id
            )
        ):
            return
        session.add(
            SearchRun(
                operation_id=row.id,
                project_id=row.project_id,
                search_query_id=query.id,
                provider=query.provider,
                executed_query=query.query_text,
                executed_filters=provider_filters(query.provider, query.filters),
                status=SearchRunStatus.FAILED,
                completed_at=datetime.now(UTC),
                provider_metadata={"error": error},
            )
        )
        event(
            session,
            row.project_id,
            "SEARCH_PARTIALLY_FAILED",
            operation_id=operation_id,
            provider=query.provider,
            error=error,
        )


@activity.defn
async def normalize_discovery(operation_id: str) -> None:
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        if "work_ids" in row.details:
            return
        await session.get(ResearchProject, row.project_id, with_for_update=True)
        payloads = await session.scalars(
            select(SearchResult.normalized_payload)
            .join(SearchRun)
            .where(SearchRun.operation_id == row.id)
            .order_by(SearchRun.provider, SearchResult.rank)
        )
        works = [ProviderWork.model_validate(payload) for payload in payloads]
        report = DiscoveryReport()
        service = LiteratureDiscoveryService(session, {})
        await service.normalize_and_persist(row.project_id, works, report)
        row.details = {**row.details, "work_ids": list(dict.fromkeys(map(str, report.work_ids)))}
        event(
            session,
            row.project_id,
            "LITERATURE_NORMALIZED",
            operation_id=operation_id,
            records=len(set(report.work_ids)),
        )


@activity.defn
async def deduplicate_discovery(operation_id: str) -> None:
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        if row.details.get("deduplicated"):
            return
        works = list(
            await session.scalars(
                select(WorkRecord)
                .where(WorkRecord.project_id == row.project_id)
                .order_by(WorkRecord.id)
            )
        )
        candidates = []
        for work in works:
            identifiers = await session.scalars(
                select(WorkIdentifier).where(WorkIdentifier.work_id == work.id)
            )
            candidates.append(
                DedupCandidate(
                    work_id=str(work.id),
                    doi=work.doi,
                    title=work.title,
                    publication_year=work.publication_year,
                    external_ids=tuple(
                        (i.identifier_type.value, i.identifier) for i in identifiers
                    ),
                )
            )
        matches = find_duplicate_matches(candidates)
        for match in matches:
            await persist_duplicate_match(
                session,
                row.project_id,
                match,
                uuid.UUID(match.work_id_a),
                uuid.UUID(match.work_id_b),
            )
        row.details = {**row.details, "deduplicated": True}
        event(
            session,
            row.project_id,
            "DEDUPLICATION_COMPLETED",
            operation_id=operation_id,
            groups=len(matches),
        )


@activity.defn
async def verify_discovery(operation_id: str) -> None:
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        work_ids = cast(list[str], row.details.get("work_ids", []))
    for work_id in work_ids:
        async with session_scope(_session_factory()) as session:
            row = await operation(session, operation_id)
            verified = cast(list[str], row.details.get("verified_work_ids", []))
            if work_id in verified:
                continue
            work = await session.get(WorkRecord, uuid.UUID(str(work_id)))
            assert work is not None and work.project_id == row.project_id
            if work.doi:
                outcome = await SourceVerificationService(list(providers().values())).verify_by_doi(
                    work.doi,
                    ProviderWork(
                        provider="canonical",
                        provider_id=str(work.id),
                        doi=work.doi,
                        title=work.title,
                        publication_year=work.publication_year,
                    ),
                )
            else:
                outcome = VerificationOutcome(
                    verification_type=WorkVerificationType.SOURCE_EXISTENCE,
                    status=WorkVerificationStatus.UNVERIFIED,
                    details={"reason": "No DOI available for identity lookup"},
                )
            await persist_verification(session, work.id, outcome)
            row.details = {**row.details, "verified_work_ids": [*verified, work_id]}
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        if not row.details.get("verification_completed"):
            row.details = {**row.details, "verification_completed": True}
            event(
                session, row.project_id, "SOURCE_VERIFICATION_COMPLETED", operation_id=operation_id
            )


@activity.defn
async def finalize_discovery(operation_id: str) -> str:
    async with session_scope(_session_factory()) as session:
        statuses = list(
            await session.scalars(
                select(SearchRun.status).where(SearchRun.operation_id == uuid.UUID(operation_id))
            )
        )
    status = "COMPLETED"
    if not statuses or all(s == SearchRunStatus.FAILED for s in statuses):
        status = "FAILED"
    elif any(s != SearchRunStatus.COMPLETED for s in statuses):
        status = "PARTIAL"
    await finish_operation(operation_id, status)
    return status

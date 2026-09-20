import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.enums import SearchRunStatus
from ranah_domain.models.search import SearchQuery, SearchResult, SearchRun, SearchStrategy
from ranah_domain.schemas.search import (
    SearchQueryCreate,
    SearchResultCreate,
    SearchRunCreate,
    SearchStrategyCreate,
)


async def create_strategy(session: AsyncSession, data: SearchStrategyCreate) -> SearchStrategy:
    strategy = SearchStrategy(**data.model_dump())
    session.add(strategy)
    await session.flush()
    return strategy


async def create_query(session: AsyncSession, data: SearchQueryCreate) -> SearchQuery:
    query = SearchQuery(**data.model_dump())
    session.add(query)
    await session.flush()
    return query


async def create_run(session: AsyncSession, data: SearchRunCreate) -> SearchRun:
    run = SearchRun(
        started_at=datetime.now(UTC), status=SearchRunStatus.RUNNING, **data.model_dump()
    )
    session.add(run)
    await session.flush()
    return run


async def complete_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    status: SearchRunStatus,
    result_count_reported: int | None = None,
    result_count_retrieved: int = 0,
    provider_metadata: dict[str, object] | None = None,
) -> SearchRun:
    run = await session.get(SearchRun, run_id)
    if run is None:
        raise ValueError(f"SearchRun {run_id} not found")
    run.status = status
    run.completed_at = datetime.now(UTC)
    run.result_count_reported = result_count_reported
    run.result_count_retrieved = result_count_retrieved
    if provider_metadata is not None:
        run.provider_metadata = provider_metadata
    await session.flush()
    return run


async def add_result(session: AsyncSession, data: SearchResultCreate) -> SearchResult:
    result = SearchResult(**data.model_dump())
    session.add(result)
    await session.flush()
    return result


async def list_results(session: AsyncSession, search_run_id: uuid.UUID) -> list[SearchResult]:
    stmt = select(SearchResult).where(SearchResult.search_run_id == search_run_id)
    return list((await session.scalars(stmt)).all())

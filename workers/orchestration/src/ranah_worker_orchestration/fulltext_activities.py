import uuid
from functools import lru_cache
from typing import cast

import httpx
from ranah_documents.fulltext import FullTextAcquisitionService
from ranah_domain.db import session_scope
from ranah_domain.enums import FullTextAcquisitionStatus
from ranah_domain.models.work import WorkRecord
from ranah_domain.repositories.fulltext import acquisition_for
from ranah_domain.storage import object_storage
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research


@lru_cache
def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True, max_redirects=3)


SETTLED = {
    FullTextAcquisitionStatus.AVAILABLE,
    FullTextAcquisitionStatus.ABSTRACT_ONLY,
    FullTextAcquisitionStatus.UNAVAILABLE,
}


@activity.defn
async def prepare_acquisition_batch(operation_id: str) -> list[str]:
    """Works still needing an attempt in this operation.

    A work is skipped once it has been attempted here, not only once it settles:
    RETRIEVAL_FAILED is a legitimate resting state, and retrying it inside the
    same run would never terminate. Retrying is a new operation's job.
    """
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        attempted = set(cast(list[str], op.details.get("attempted", [])))
        batch_size = int(str(op.details["batch_size"]))
        pending = []
        for raw in cast(list[str], op.details["work_ids"]):
            if raw in attempted:
                continue
            row = await acquisition_for(session, op.project_id, uuid.UUID(raw))
            if row is not None and row.status in SETTLED:
                continue
            pending.append(raw)
            if len(pending) >= batch_size:
                break
        return pending


@activity.defn
async def acquire_full_text_batch(operation_id: str, work_ids: list[str]) -> dict[str, str]:
    """One committed transaction per work: a later failure never discards an
    asset that was already retrieved and stored."""
    outcomes: dict[str, str] = {}
    for work_id in work_ids:
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            work = await session.get(WorkRecord, uuid.UUID(work_id))
            if work is None or work.project_id != op.project_id:
                raise ApplicationError("Work is not part of this project", non_retryable=True)
            service = FullTextAcquisitionService(session, object_storage(), client=http_client())
            outcome = await service.acquire(work)
            outcomes[work_id] = outcome.status.value
            attempted = cast(list[str], op.details.get("attempted", []))
            op.details = {**op.details, "attempted": [*attempted, work_id]}
            research.event(
                session,
                op.project_id,
                "FULL_TEXT_ACQUISITION_ATTEMPTED",
                work_id=work_id,
                status=outcome.status.value,
                asset_id=str(outcome.asset_id) if outcome.asset_id else None,
            )
    return outcomes


@activity.defn
async def calculate_acquisition_progress(operation_id: str) -> dict[str, int]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        counts: dict[str, int] = {status.value: 0 for status in FullTextAcquisitionStatus}
        work_ids = cast(list[str], op.details["work_ids"])
        for raw in work_ids:
            row = await acquisition_for(session, op.project_id, uuid.UUID(raw))
            status = row.status if row else FullTextAcquisitionStatus.NOT_REQUESTED
            counts[status.value] += 1
        progress = {"total": len(work_ids), **counts}
        op.details = {**op.details, "progress": progress}
        return progress

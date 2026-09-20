import uuid
from typing import cast

from ranah_documents.parsing import DocumentParseError
from ranah_documents.parsing_service import DocumentParsingService
from ranah_domain.db import session_scope
from ranah_domain.enums import FullTextAssetStatus
from ranah_domain.models.fulltext import FullTextAsset
from ranah_domain.repositories.fulltext import latest_asset, parsed_document_for
from ranah_domain.storage import object_storage
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research


@activity.defn
async def prepare_parsing_batch(operation_id: str) -> list[str]:
    """Assets for this operation's works that still need a parse attempt."""
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        attempted = set(cast(list[str], op.details.get("attempted", [])))
        batch_size = int(str(op.details["batch_size"]))
        pending = []
        for raw in cast(list[str], op.details["work_ids"]):
            asset = await latest_asset(session, uuid.UUID(raw))
            if asset is None or str(asset.id) in attempted:
                continue
            if await parsed_document_for(session, asset.id) is not None:
                continue
            pending.append(str(asset.id))
            if len(pending) >= batch_size:
                break
        return pending


@activity.defn
async def parse_assets(operation_id: str, asset_ids: list[str]) -> dict[str, str]:
    """One transaction per asset. A malformed PDF fails that asset only; the
    asset itself is preserved for a later parser."""
    outcomes: dict[str, str] = {}
    for asset_id in asset_ids:
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            asset = await session.get(FullTextAsset, uuid.UUID(asset_id))
            if asset is None or asset.project_id != op.project_id:
                raise ApplicationError("Asset is not part of this project", non_retryable=True)
            attempted = cast(list[str], op.details.get("attempted", []))
            op.details = {**op.details, "attempted": [*attempted, asset_id]}
            try:
                document = await DocumentParsingService(session, object_storage()).parse_asset(
                    asset
                )
            except DocumentParseError as exc:
                outcomes[asset_id] = "FAILED"
                research.event(
                    session,
                    op.project_id,
                    "FULL_TEXT_PARSE_FAILED",
                    work_id=str(asset.work_id),
                    asset_id=asset_id,
                    error=str(exc),
                )
                continue
            outcomes[asset_id] = document.status
            research.event(
                session,
                op.project_id,
                "FULL_TEXT_PARSED",
                work_id=str(asset.work_id),
                asset_id=asset_id,
                parsed_document_id=str(document.id),
                pages=document.page_count,
                status=document.status,
            )
    return outcomes


@activity.defn
async def calculate_parsing_progress(operation_id: str) -> dict[str, int]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        work_ids = cast(list[str], op.details["work_ids"])
        counts = {"total": len(work_ids), "parsed": 0, "failed": 0, "missing_asset": 0}
        for raw in work_ids:
            asset = await session.scalar(
                select(FullTextAsset)
                .where(FullTextAsset.work_id == uuid.UUID(raw))
                .order_by(FullTextAsset.retrieved_at.desc())
                .limit(1)
            )
            if asset is None:
                counts["missing_asset"] += 1
            elif asset.status == FullTextAssetStatus.PARSED:
                counts["parsed"] += 1
            elif asset.status == FullTextAssetStatus.FAILED:
                counts["failed"] += 1
        op.details = {**op.details, "progress": counts}
        return counts

import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, UploadFile
from ranah_documents.fulltext import (
    MAX_ASSET_BYTES,
    FullTextAcquisitionService,
    FullTextRejected,
)
from ranah_domain.enums import FullTextAcquisitionStatus, FullTextAssetStatus
from ranah_domain.models.fulltext import FullTextAsset
from ranah_domain.models.work import WorkRecord
from ranah_domain.repositories.fulltext import (
    acquisition_statuses,
    chunks_for,
    full_text_view,
    latest_asset,
    latest_parsed_document,
)
from ranah_domain.repositories.screening import canonical_ids, effective_decisions, latest_protocol
from ranah_domain.storage import object_storage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_api.projects import (
    DB,
    Principal,
    append_event,
    error,
    scoped_project,
    start_operation,
)

router = APIRouter(prefix="/projects", tags=["Full text"])


def batch_size() -> int:
    return max(1, min(50, int(os.environ.get("FULL_TEXT_BATCH_SIZE", "5"))))


async def scoped_work(
    session: AsyncSession, project_id: uuid.UUID, work_id: uuid.UUID
) -> WorkRecord:
    work = await session.get(WorkRecord, work_id)
    if work is None or work.project_id != project_id:
        raise error(404, "NOT_FOUND", "Work not found in this project")
    return work


@router.get("/{project_id}/works/{work_id}/full-text")
async def get_full_text(
    project_id: uuid.UUID, work_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    await scoped_project(session, user, project_id)
    await scoped_work(session, project_id, work_id)
    return await full_text_view(session, project_id, work_id)


@router.get("/{project_id}/full-text/status")
async def status_overview(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Per-work acquisition state for the whole canonical corpus. Works with no
    attempt are reported as NOT_REQUESTED rather than omitted."""
    await scoped_project(session, user, project_id)
    statuses = await acquisition_statuses(session, project_id)
    work_ids = await canonical_ids(session, project_id)
    counts: dict[str, int] = {status.value: 0 for status in FullTextAcquisitionStatus}
    items = []
    for work_id in work_ids:
        status = statuses.get(work_id, FullTextAcquisitionStatus.NOT_REQUESTED)
        counts[status.value] += 1
        items.append({"work_id": work_id, "status": status})
    return {"total": len(work_ids), "counts": counts, "items": items}


@router.post("/{project_id}/works/{work_id}/full-text/upload", status_code=201)
async def upload_full_text(
    project_id: uuid.UUID,
    work_id: uuid.UUID,
    session: DB,
    user: Principal,
    file: Annotated[UploadFile, File()],
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    work = await scoped_work(session, project_id, work_id)
    content = await file.read(MAX_ASSET_BYTES + 1)
    service = FullTextAcquisitionService(session, object_storage())
    try:
        asset, created = await service.upload(work, content, uploaded_by=user.id)
    except FullTextRejected as exc:
        raise error(422, "USER_INPUT_ERROR", str(exc)) from exc
    append_event(
        session,
        project,
        user,
        "FULL_TEXT_UPLOADED",
        work_id=str(work_id),
        asset_id=str(asset.id),
        sha256=asset.sha256,
        stored_new_file=created,
    )
    await session.flush()
    return {**await full_text_view(session, project_id, work_id), "stored_new_file": created}


@router.post("/{project_id}/works/{work_id}/full-text/acquire", status_code=202)
async def acquire_full_text(
    project_id: uuid.UUID, work_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    """Remote retrieval runs in a durable workflow; HTTP never downloads."""
    project = await scoped_project(session, user, project_id, write=True)
    await scoped_work(session, project_id, work_id)
    return await start_operation(
        session,
        project,
        "full_text",
        {"work_ids": [str(work_id)], "records_total": 1, "batch_size": batch_size()},
    )


@router.post("/{project_id}/full-text/acquire", status_code=202)
async def acquire_included(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Acquire full text for every work that passed title/abstract screening."""
    project = await scoped_project(session, user, project_id, write=True)
    protocol = await latest_protocol(session, project_id)
    if not protocol or protocol.status != "APPROVED":
        raise error(409, "WORKFLOW_CONFLICT", "Approve a protocol and screen titles first")
    effective = await effective_decisions(session, protocol.id)
    work_ids = [
        str(work_id)
        for work_id, decision in effective.items()
        if decision.decision in ("INCLUDE", "UNCERTAIN")
    ]
    if not work_ids:
        raise error(
            409, "WORKFLOW_CONFLICT", "No records passed title/abstract screening for this protocol"
        )
    return await start_operation(
        session,
        project,
        "full_text",
        {"work_ids": work_ids, "records_total": len(work_ids), "batch_size": batch_size()},
    )


async def _works_with_assets(session: AsyncSession, project_id: uuid.UUID) -> list[str]:
    rows = await session.scalars(
        select(FullTextAsset.work_id)
        .where(
            FullTextAsset.project_id == project_id,
            FullTextAsset.status != FullTextAssetStatus.REMOVED,
        )
        .distinct()
    )
    return [str(work_id) for work_id in rows]


@router.post("/{project_id}/works/{work_id}/full-text/parse", status_code=202)
async def parse_work_full_text(
    project_id: uuid.UUID, work_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    await scoped_work(session, project_id, work_id)
    if await latest_asset(session, work_id) is None:
        raise error(409, "WORKFLOW_CONFLICT", "Obtain or upload full text before parsing")
    return await start_operation(
        session,
        project,
        "parsing",
        {"work_ids": [str(work_id)], "records_total": 1, "batch_size": batch_size()},
    )


@router.post("/{project_id}/full-text/parse", status_code=202)
async def parse_project_full_text(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Parse every stored asset in the project that has not been parsed yet."""
    project = await scoped_project(session, user, project_id, write=True)
    work_ids = await _works_with_assets(session, project_id)
    if not work_ids:
        raise error(409, "WORKFLOW_CONFLICT", "No full-text assets are stored for this project")
    return await start_operation(
        session,
        project,
        "parsing",
        {"work_ids": work_ids, "records_total": len(work_ids), "batch_size": batch_size()},
    )


@router.get("/{project_id}/works/{work_id}/full-text/chunks")
async def get_chunks(
    project_id: uuid.UUID, work_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    """Parsed passages with the page and section each one came from."""
    await scoped_project(session, user, project_id)
    await scoped_work(session, project_id, work_id)
    document = await latest_parsed_document(session, work_id)
    if document is None:
        return {"parsed_document_id": None, "chunks": []}
    return {
        "parsed_document_id": document.id,
        "parser": f"{document.parser_name} v{document.parser_version}",
        "page_count": document.page_count,
        "warnings": document.warnings,
        "chunks": [
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_path": chunk.section_path,
                "section_type": chunk.section_type,
                "text": chunk.text,
                "token_count": chunk.token_count,
            }
            for chunk in await chunks_for(session, document.id)
        ],
    }

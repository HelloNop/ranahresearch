import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.enums import FullTextAcquisitionStatus, FullTextAssetStatus
from ranah_domain.models.fulltext import (
    DocumentChunk,
    FullTextAcquisition,
    FullTextAsset,
    ParsedDocument,
)


async def acquisition_for(
    session: AsyncSession, project_id: uuid.UUID, work_id: uuid.UUID
) -> FullTextAcquisition | None:
    return cast(
        FullTextAcquisition | None,
        await session.scalar(
            select(FullTextAcquisition).where(
                FullTextAcquisition.project_id == project_id,
                FullTextAcquisition.work_id == work_id,
            )
        ),
    )


async def acquisition_statuses(
    session: AsyncSession, project_id: uuid.UUID
) -> dict[uuid.UUID, FullTextAcquisitionStatus]:
    """Works with no row have never been requested, which is itself an honest state."""
    rows = await session.scalars(
        select(FullTextAcquisition).where(FullTextAcquisition.project_id == project_id)
    )
    return {row.work_id: row.status for row in rows}


async def assets_for(session: AsyncSession, work_id: uuid.UUID) -> list[FullTextAsset]:
    rows = await session.scalars(
        select(FullTextAsset)
        .where(
            FullTextAsset.work_id == work_id, FullTextAsset.status != FullTextAssetStatus.REMOVED
        )
        .order_by(FullTextAsset.retrieved_at.desc(), FullTextAsset.id)
    )
    return list(rows)


async def latest_asset(session: AsyncSession, work_id: uuid.UUID) -> FullTextAsset | None:
    assets = await assets_for(session, work_id)
    return assets[0] if assets else None


async def parsed_document_for(session: AsyncSession, asset_id: uuid.UUID) -> ParsedDocument | None:
    return cast(
        ParsedDocument | None,
        await session.scalar(
            select(ParsedDocument)
            .where(ParsedDocument.full_text_asset_id == asset_id)
            .order_by(ParsedDocument.created_at.desc(), ParsedDocument.id)
            .limit(1)
        ),
    )


async def latest_parsed_document(
    session: AsyncSession, work_id: uuid.UUID
) -> ParsedDocument | None:
    """The parsed document of this work's current asset, if it has been parsed."""
    asset = await latest_asset(session, work_id)
    return await parsed_document_for(session, asset.id) if asset else None


async def chunks_for(session: AsyncSession, parsed_document_id: uuid.UUID) -> list[DocumentChunk]:
    rows = await session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.parsed_document_id == parsed_document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(rows)


def asset_view(row: FullTextAsset) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def full_text_view(
    session: AsyncSession, project_id: uuid.UUID, work_id: uuid.UUID
) -> dict[str, Any]:
    acquisition = await acquisition_for(session, project_id, work_id)
    assets = await assets_for(session, work_id)
    parsed = await parsed_document_for(session, assets[0].id) if assets else None
    return {
        "work_id": work_id,
        "status": acquisition.status if acquisition else FullTextAcquisitionStatus.NOT_REQUESTED,
        "error": acquisition.error if acquisition else None,
        "last_attempt_at": acquisition.last_attempt_at if acquisition else None,
        "attempts": acquisition.attempts if acquisition else [],
        "assets": [asset_view(asset) for asset in assets],
        "parsed_document": {
            "id": parsed.id,
            "parser_name": parsed.parser_name,
            "parser_version": parsed.parser_version,
            "page_count": parsed.page_count,
            "status": parsed.status,
            "warnings": parsed.warnings,
            "sections": parsed.structure.get("sections", []),
        }
        if parsed
        else None,
    }

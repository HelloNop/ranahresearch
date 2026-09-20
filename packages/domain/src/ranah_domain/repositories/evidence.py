import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.enums import EvidenceStatus, EvidenceValueType, EvidenceVerificationStatus
from ranah_domain.models.evidence import (
    Evidence,
    EvidenceProvenance,
    EvidenceVerification,
    ExtractionSchema,
)
from ranah_domain.models.study import Study


async def latest_schema(session: AsyncSession, project_id: uuid.UUID) -> ExtractionSchema | None:
    return cast(
        ExtractionSchema | None,
        await session.scalar(
            select(ExtractionSchema)
            .where(ExtractionSchema.project_id == project_id)
            .order_by(ExtractionSchema.version.desc())
            .limit(1)
        ),
    )


async def current_evidence(
    session: AsyncSession, project_id: uuid.UUID, study_id: uuid.UUID | None = None
) -> list[Evidence]:
    stmt = select(Evidence).where(
        Evidence.project_id == project_id, Evidence.status == EvidenceStatus.CURRENT
    )
    if study_id:
        stmt = stmt.where(Evidence.study_id == study_id)
    rows = await session.scalars(stmt.order_by(Evidence.study_id, Evidence.field_name))
    return list(rows)


async def provenance_for(session: AsyncSession, evidence_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(EvidenceProvenance)
        .where(EvidenceProvenance.evidence_id == evidence_id)
        .order_by(EvidenceProvenance.created_at, EvidenceProvenance.id)
    )
    return [
        {
            "work_id": row.work_id,
            "parsed_document_id": row.parsed_document_id,
            "chunk_id": row.chunk_id,
            "page": row.page,
            "section": row.section,
            "evidence_text": row.evidence_text,
        }
        for row in rows
    ]


async def verifications_for(session: AsyncSession, evidence_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(EvidenceVerification)
        .where(EvidenceVerification.evidence_id == evidence_id)
        .order_by(EvidenceVerification.created_at.desc(), EvidenceVerification.id.desc())
    )
    return [
        {
            "id": row.id,
            "method": row.verification_method,
            "status": row.status,
            "confidence": row.confidence,
            "findings": row.findings,
            "notes": row.notes,
            "reviewer_id": row.reviewer_id,
            "agent_run_id": row.agent_run_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def history_for_field(
    session: AsyncSession, study_id: uuid.UUID, field_name: str
) -> list[Evidence]:
    """Every version of one field, newest first. AI extractions stay visible
    after a human correction supersedes them."""
    rows = await session.scalars(
        select(Evidence)
        .where(Evidence.study_id == study_id, Evidence.field_name == field_name)
        .order_by(Evidence.created_at.desc(), Evidence.id.desc())
    )
    return list(rows)


async def evidence_view(
    session: AsyncSession, row: Evidence, *, include_history: bool = False
) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": row.id,
        "study_id": row.study_id,
        "work_id": row.work_id,
        "field_name": row.field_name,
        "evidence_type": row.evidence_type,
        "value": row.value_json,
        "unit": row.unit,
        "value_type": row.value_type,
        "derivation": row.derivation,
        "confidence": row.confidence,
        "verification_status": row.verification_status,
        "status": row.status,
        "notes": row.notes,
        "extractor_run_id": row.extractor_run_id,
        "entered_by": row.entered_by,
        "created_at": row.created_at,
        "provenance": await provenance_for(session, row.id),
        "verifications": await verifications_for(session, row.id),
    }
    if include_history:
        view["history"] = [
            {
                "id": previous.id,
                "value": previous.value_json,
                "value_type": previous.value_type,
                "status": previous.status,
                "entered_by": previous.entered_by,
                "extractor_run_id": previous.extractor_run_id,
                "notes": previous.notes,
                "created_at": previous.created_at,
            }
            for previous in await history_for_field(session, row.study_id, row.field_name)
        ]
    return view


async def matrix(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """Study-per-row evidence matrix with the columns the schema defines."""
    schema = await latest_schema(session, project_id)
    columns = (
        [
            {"name": field["name"], "label": field["label"], "kind": field["kind"]}
            for field in schema.schema_json.get("fields", [])
        ]
        if schema
        else []
    )
    studies = list(
        await session.scalars(
            select(Study)
            .where(Study.project_id == project_id, Study.status != "MERGED")
            .order_by(Study.study_label)
        )
    )
    rows = []
    all_evidence = await current_evidence(session, project_id)
    by_study: dict[uuid.UUID, list[Evidence]] = {}
    for item in all_evidence:
        by_study.setdefault(item.study_id, []).append(item)

    for study in studies:
        items = by_study.get(study.id, [])
        cells = {}
        for item in items:
            cells[item.field_name] = {
                "evidence_id": item.id,
                "value": item.value_json,
                "unit": item.unit,
                "value_type": item.value_type,
                "verification_status": item.verification_status,
                "has_provenance": bool(await provenance_for(session, item.id)),
            }
        rows.append(
            {
                "study_id": study.id,
                "study_label": study.study_label,
                "title": study.title,
                "study_type": study.study_type,
                "status": study.status,
                "cells": cells,
                "extraction_status": "EXTRACTED" if items else "NOT_EXTRACTED",
                "needs_review": any(
                    item.verification_status == EvidenceVerificationStatus.CONFLICT
                    for item in items
                ),
                "missing_count": sum(
                    item.value_type == EvidenceValueType.MISSING for item in items
                ),
            }
        )
    return {
        "extraction_schema_id": schema.id if schema else None,
        "columns": columns,
        "rows": rows,
    }

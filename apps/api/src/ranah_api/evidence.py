import os
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import Field
from ranah_domain.enums import (
    EvidenceStatus,
    EvidenceValueType,
    EvidenceVerificationStatus,
)
from ranah_domain.models.evidence import Evidence, EvidenceProvenance
from ranah_domain.models.study import Study
from ranah_domain.repositories.evidence import (
    current_evidence,
    evidence_view,
    latest_schema,
    matrix,
)
from ranah_domain.repositories.screening import final_included_work_ids, latest_protocol
from ranah_domain.repositories.study import studies_for_project, works_for_study
from ranah_domain.schemas.screening import StrictModel, Text
from ranah_evidence.validation import SEVERITY_ERROR, validate_study_values
from sqlalchemy import select

from ranah_api.projects import (
    DB,
    Principal,
    append_event,
    error,
    scoped_project,
    start_operation,
)

router = APIRouter(prefix="/projects", tags=["Evidence"])


class Correction(StrictModel):
    value: Any = None
    unit: str | None = None
    value_type: Literal["USER_ENTERED", "MISSING"] = "USER_ENTERED"
    reason: Text = Field(default="Human correction")
    evidence_text: str | None = None
    page: int | None = None
    section: str | None = None


@router.get("/{project_id}/evidence")
async def list_evidence(
    project_id: uuid.UUID,
    session: DB,
    user: Principal,
    study_id: uuid.UUID | None = None,
    field_name: str | None = None,
    verification_status: EvidenceVerificationStatus | None = None,
    value_type: EvidenceValueType | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    await scoped_project(session, user, project_id)
    rows = await current_evidence(session, project_id, study_id)
    if field_name:
        rows = [row for row in rows if row.field_name == field_name]
    if verification_status:
        rows = [row for row in rows if row.verification_status == verification_status]
    if value_type:
        rows = [row for row in rows if row.value_type == value_type]
    return [await evidence_view(session, row) for row in rows[offset : offset + limit]]


@router.get("/{project_id}/evidence/matrix")
async def evidence_matrix(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    return await matrix(session, project_id)


@router.get("/{project_id}/evidence/progress")
async def extraction_progress(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Counts for the extraction workspace, including honest missing-text states."""
    await scoped_project(session, user, project_id)
    protocol = await latest_protocol(session, project_id)
    included = set(await final_included_work_ids(session, protocol.id)) if protocol else set()
    studies = await studies_for_project(session, project_id)
    rows = await current_evidence(session, project_id)
    by_study: dict[uuid.UUID, list[Evidence]] = {}
    for row in rows:
        by_study.setdefault(row.study_id, []).append(row)

    included_studies = 0
    extracted = 0
    needs_review = 0
    missing_full_text = 0
    for study in studies:
        works = {link.work_id for link in await works_for_study(session, study.id)}
        if not works & included:
            continue
        included_studies += 1
        items = by_study.get(study.id, [])
        if items:
            extracted += 1
            if any(
                item.verification_status == EvidenceVerificationStatus.CONFLICT for item in items
            ):
                needs_review += 1
        else:
            missing_full_text += 1
    return {
        "included_studies": included_studies,
        "extraction_complete": extracted,
        "needs_review": needs_review,
        "awaiting_extraction": missing_full_text,
        "evidence_items": len(rows),
        "missing_values": sum(row.value_type == EvidenceValueType.MISSING for row in rows),
    }


@router.get("/{project_id}/studies/{study_id}/evidence")
async def study_evidence(
    project_id: uuid.UUID, study_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    await scoped_project(session, user, project_id)
    study = await session.get(Study, study_id)
    if study is None or study.project_id != project_id:
        raise error(404, "NOT_FOUND", "Study not found in this project")
    rows = await current_evidence(session, project_id, study_id)
    return {
        "study_id": study_id,
        "study_label": study.study_label,
        "evidence": [await evidence_view(session, row, include_history=True) for row in rows],
    }


@router.post("/{project_id}/extraction/start", status_code=202)
async def start_extraction(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    protocol = await latest_protocol(session, project_id)
    if not protocol or protocol.status != "APPROVED":
        raise error(409, "WORKFLOW_CONFLICT", "Approve a protocol first")
    if not await final_included_work_ids(session, protocol.id):
        raise error(
            409,
            "WORKFLOW_CONFLICT",
            "Complete full-text screening first; extraction runs on finally included studies",
        )
    return await start_operation(
        session,
        project,
        "extraction",
        {
            "study_ids": [],
            "batch_size": max(1, min(20, int(os.environ.get("EXTRACTION_BATCH_SIZE", "3")))),
        },
    )


@router.post("/{project_id}/evidence/{evidence_id}/correct", status_code=201)
async def correct_evidence(
    project_id: uuid.UUID,
    evidence_id: uuid.UUID,
    data: Correction,
    session: DB,
    user: Principal,
) -> Any:
    """A correction supersedes; it never overwrites the AI's extraction."""
    project = await scoped_project(session, user, project_id, write=True)
    row = await session.get(Evidence, evidence_id)
    if row is None or row.project_id != project_id:
        raise error(404, "NOT_FOUND", "Evidence not found in this project")
    if row.status != EvidenceStatus.CURRENT:
        raise error(409, "WORKFLOW_CONFLICT", "This evidence has already been superseded")

    value_type = EvidenceValueType(data.value_type)
    if value_type == EvidenceValueType.USER_ENTERED and data.value is None:
        raise error(422, "USER_INPUT_ERROR", "Provide a value, or record the field as missing")
    if value_type == EvidenceValueType.USER_ENTERED:
        findings = validate_study_values(
            {row.field_name: data.value}, {row.field_name: data.unit or row.unit}
        )
        failed = [f for f in findings if f.severity == SEVERITY_ERROR]
        if failed:
            raise error(422, "SCIENTIFIC_VALIDATION_ERROR", failed[0].message)

    replacement = Evidence(
        project_id=project_id,
        study_id=row.study_id,
        work_id=row.work_id,
        extraction_schema_id=row.extraction_schema_id,
        evidence_type=row.evidence_type,
        field_name=row.field_name,
        value_json=data.value if value_type == EvidenceValueType.USER_ENTERED else None,
        unit=data.unit or row.unit,
        value_type=value_type,
        confidence=None,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
        status=EvidenceStatus.CURRENT,
        entered_by=user.id,
        notes=data.reason,
    )
    session.add(replacement)
    await session.flush()
    if data.evidence_text:
        session.add(
            EvidenceProvenance(
                evidence_id=replacement.id,
                work_id=row.work_id,
                page=data.page,
                section=data.section,
                evidence_text=data.evidence_text,
            )
        )
    row.status = EvidenceStatus.SUPERSEDED
    row.superseded_by = replacement.id
    append_event(
        session,
        project,
        user,
        "EVIDENCE_CORRECTED",
        evidence_id=str(evidence_id),
        replacement_id=str(replacement.id),
        field_name=row.field_name,
        reason=data.reason,
    )
    await session.flush()
    return await evidence_view(session, replacement, include_history=True)


@router.get("/{project_id}/extraction-schema")
async def get_schema(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    schema = await latest_schema(session, project_id)
    if schema is None:
        return None
    return {
        "id": schema.id,
        "version": schema.version,
        "status": schema.status,
        "protocol_id": schema.protocol_id,
        "fields": schema.schema_json.get("fields", []),
    }


@router.get("/{project_id}/evidence/{evidence_id}")
async def get_evidence(
    project_id: uuid.UUID, evidence_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    await scoped_project(session, user, project_id)
    row = await session.get(Evidence, evidence_id)
    if row is None or row.project_id != project_id:
        raise error(404, "NOT_FOUND", "Evidence not found in this project")
    return await evidence_view(session, row, include_history=True)


@router.get("/{project_id}/evidence-conflicts")
async def conflicts(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Items a deterministic check or the reviewer flagged, for human resolution."""
    await scoped_project(session, user, project_id)
    rows = await session.scalars(
        select(Evidence).where(
            Evidence.project_id == project_id,
            Evidence.status == EvidenceStatus.CURRENT,
            Evidence.verification_status == EvidenceVerificationStatus.CONFLICT,
        )
    )
    return [await evidence_view(session, row) for row in rows]

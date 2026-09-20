"""Evidence validation: deterministic checks first, then independent review.

Deterministic findings settle arithmetic facts without an LLM call. The reviewer
then inspects the source passages itself. Neither step ever rewrites a value: a
disagreement becomes a CONFLICT verification event for a human to resolve.
"""

import uuid
from typing import Any, cast

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.evidence_review import (
    EvidenceReviewInput,
    EvidenceReviewOutput,
    EvidenceUnderReview,
    review_registry,
)
from ranah_agents.runtime import run_agent
from ranah_agents.tools import ToolRegistry
from ranah_domain.db import session_scope
from ranah_domain.enums import (
    AgentRunStatus,
    EvidenceStatus,
    EvidenceValueType,
    EvidenceVerificationStatus,
)
from ranah_domain.models.evidence import (
    Evidence,
    EvidenceProvenance,
    EvidenceVerification,
    ExtractionSchema,
)
from ranah_domain.models.study import Study
from ranah_evidence.schema import ExtractionSchemaDefinition
from ranah_evidence.validation import SEVERITY_ERROR, validate_study_values
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.extraction_activities import _study_passages

REVIEWABLE_TYPES = (EvidenceValueType.REPORTED, EvidenceValueType.DERIVED)


async def _current_evidence(session: AsyncSession, study_id: uuid.UUID) -> list[Evidence]:
    rows = await session.scalars(
        select(Evidence)
        .where(Evidence.study_id == study_id, Evidence.status == EvidenceStatus.CURRENT)
        .order_by(Evidence.field_name)
    )
    return list(rows)


@activity.defn
async def validate_project_evidence(operation_id: str) -> dict[str, int]:
    """Deterministic checks over each study's current evidence."""
    counts = {"checked": 0, "errors": 0, "warnings": 0}
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        for raw in cast(list[str], op.details.get("study_ids", [])):
            study_id = uuid.UUID(raw)
            rows = await _current_evidence(session, study_id)
            if not rows:
                continue
            values = {row.field_name: row.value_json for row in rows}
            units = {row.field_name: row.unit for row in rows}
            findings = validate_study_values(values, units)
            by_field: dict[str, list[dict[str, Any]]] = {}
            for finding in findings:
                by_field.setdefault(finding.field_name, []).append(
                    {
                        "code": finding.code,
                        "severity": finding.severity,
                        "message": finding.message,
                    }
                )
            for row in rows:
                if row.value_type == EvidenceValueType.MISSING:
                    continue
                counts["checked"] += 1
                field_findings = by_field.get(row.field_name, [])
                failed = [f for f in field_findings if f["severity"] == SEVERITY_ERROR]
                counts["errors"] += len(failed)
                counts["warnings"] += len(field_findings) - len(failed)
                session.add(
                    EvidenceVerification(
                        evidence_id=row.id,
                        verification_method="DETERMINISTIC_RULES",
                        status=EvidenceVerificationStatus.CONFLICT
                        if failed
                        else EvidenceVerificationStatus.PARTIAL,
                        findings=field_findings,
                        notes="Arithmetic and range checks"
                        if field_findings
                        else "No deterministic rule violated",
                    )
                )
                if failed:
                    row.verification_status = EvidenceVerificationStatus.CONFLICT
        op.details = {**op.details, "validation": counts}
        research.event(session, op.project_id, "EVIDENCE_VALIDATED", **counts)
    return counts


@activity.defn
async def review_evidence(operation_id: str) -> dict[str, int]:
    """Independent reviewer pass, one study per transaction."""
    counts = {"verified": 0, "partial": 0, "conflict": 0, "unverified": 0}
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        study_ids = cast(list[str], op.details.get("study_ids", []))
        schema_id = op.details.get("extraction_schema_id")

    for raw in study_ids:
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            study = await session.get(Study, uuid.UUID(raw))
            if study is None:
                continue
            rows = [
                row
                for row in await _current_evidence(session, study.id)
                if row.value_type in REVIEWABLE_TYPES and row.value_json is not None
            ]
            if not rows:
                continue
            schema_row = (
                await session.get(ExtractionSchema, uuid.UUID(str(schema_id)))
                if schema_id
                else None
            )
            labels = {}
            if schema_row is not None:
                definition = ExtractionSchemaDefinition.model_validate(schema_row.schema_json)
                labels = {field.name: field.label for field in definition.fields}

            passages = await _study_passages(
                session,
                study,
                ExtractionSchemaDefinition.model_validate(schema_row.schema_json).fields
                if schema_row
                else [],
            )
            if not passages:
                continue

            payload = EvidenceReviewInput(
                study_id=study.id,
                study_label=study.study_label,
                items=[
                    EvidenceUnderReview(
                        evidence_id=row.id,
                        field_name=row.field_name,
                        field_label=labels.get(row.field_name, row.field_name),
                        value=row.value_json,
                        unit=row.unit,
                        value_type=row.value_type.value,
                        derivation=row.derivation,
                    )
                    for row in rows
                ],
                passages=passages,
            )
            result = await run_agent(
                session,
                review_registry(),
                ContextBuilder(ToolRegistry(), research.gateway()),
                name="evidence_reviewer",
                version="1",
                project_id=op.project_id,
                task=AgentTask(
                    task_type="evidence_reviewer", payload=payload.model_dump(mode="json")
                ),
                workflow_id=op.temporal_workflow_id,
            )
            if result.status != AgentRunStatus.SUCCESS or not isinstance(
                result.structured_output, EvidenceReviewOutput
            ):
                # A reviewer outage leaves values unverified rather than falsely verified.
                continue

            by_id = {row.id: row for row in rows}
            for verdict in result.structured_output.verdicts:
                row = by_id[verdict.evidence_id]
                status = EvidenceVerificationStatus(verdict.status)
                session.add(
                    EvidenceVerification(
                        evidence_id=row.id,
                        verification_method="EVIDENCE_REVIEWER_AGENT",
                        status=status,
                        confidence=verdict.confidence,
                        findings=[
                            {
                                "reason": verdict.reason,
                                "source_check": list(verdict.source_check),
                                "corrected_value": verdict.corrected_value,
                            }
                        ],
                        notes=verdict.reason,
                        agent_run_id=result.agent_run_id,
                    )
                )
                # A deterministic error is never downgraded by a model's opinion.
                if row.verification_status != EvidenceVerificationStatus.CONFLICT:
                    row.verification_status = status
                counts[verdict.status.lower()] += 1
            research.event(
                session,
                op.project_id,
                "EVIDENCE_REVIEWED",
                study_id=raw,
                agent_run_id=str(result.agent_run_id),
            )

    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        op.details = {**op.details, "review": counts}
    return counts


@activity.defn
async def recheck_evidence(evidence_id: str) -> str:
    """Re-run deterministic checks for one item after a human correction."""
    async with session_scope(activities._session_factory()) as session:
        row = await session.get(Evidence, uuid.UUID(evidence_id))
        if row is None:
            return "MISSING"
        provenance = await session.scalars(
            select(EvidenceProvenance).where(EvidenceProvenance.evidence_id == row.id)
        )
        findings = validate_study_values(
            {row.field_name: row.value_json}, {row.field_name: row.unit}
        )
        failed = [f for f in findings if f.severity == SEVERITY_ERROR]
        status = (
            EvidenceVerificationStatus.CONFLICT
            if failed
            else EvidenceVerificationStatus.VERIFIED
            if list(provenance)
            else EvidenceVerificationStatus.UNVERIFIED
        )
        session.add(
            EvidenceVerification(
                evidence_id=row.id,
                verification_method="DETERMINISTIC_RULES",
                status=status,
                findings=[
                    {"code": f.code, "severity": f.severity, "message": f.message} for f in findings
                ],
                notes="Rechecked after correction",
            )
        )
        row.verification_status = status
        return status.value

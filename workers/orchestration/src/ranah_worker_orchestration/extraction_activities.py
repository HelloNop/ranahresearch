"""Evidence extraction, one study at a time.

Each study is its own transaction, so a failure at study 12 leaves studies 1-11
persisted. Extraction reads only from studies whose full-text screening ended in
INCLUDE, and only from passages retrieved per field, never a whole-document dump.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.evidence import (
    ExtractionField,
    ExtractionInput,
    ExtractionOutput,
    ExtractionPassage,
    extraction_registry,
)
from ranah_agents.runtime import run_agent
from ranah_agents.tools import ToolRegistry
from ranah_documents.retrieval import select_passages
from ranah_domain.db import session_scope
from ranah_domain.enums import (
    AgentRunStatus,
    EvidenceStatus,
    EvidenceValueType,
    EvidenceVerificationStatus,
    ExtractionSchemaStatus,
)
from ranah_domain.models.evidence import (
    Evidence,
    EvidenceProvenance,
    ExtractionSchema,
)
from ranah_domain.models.project import ResearchFramework
from ranah_domain.models.study import Study
from ranah_domain.repositories.fulltext import chunks_for, latest_parsed_document
from ranah_domain.repositories.screening import final_included_work_ids, latest_protocol
from ranah_domain.repositories.study import works_for_study
from ranah_evidence.schema import ExtractionSchemaDefinition, SchemaField, schema_payload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research

PASSAGES_PER_FIELD = 3
MAX_PASSAGES = 24


@activity.defn
async def ensure_extraction_schema(operation_id: str) -> str:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        existing = await session.scalar(
            select(ExtractionSchema)
            .where(ExtractionSchema.project_id == op.project_id)
            .order_by(ExtractionSchema.version.desc())
            .limit(1)
        )
        protocol = await latest_protocol(session, op.project_id)
        if protocol is None:
            raise ApplicationError("An approved protocol is required", non_retryable=True)
        if existing is not None and existing.protocol_id == protocol.id:
            op.details = {**op.details, "extraction_schema_id": str(existing.id)}
            return str(existing.id)
        framework = await session.get(ResearchFramework, protocol.framework_id)
        if framework is None:
            raise ApplicationError("Protocol framework is missing", non_retryable=True)
        if existing is not None:
            existing.status = ExtractionSchemaStatus.SUPERSEDED
        row = ExtractionSchema(
            project_id=op.project_id,
            protocol_id=protocol.id,
            version=existing.version + 1 if existing else 1,
            status=ExtractionSchemaStatus.APPROVED,
            schema_json=schema_payload(protocol.research_question, framework.framework_type.value),
            approved_at=datetime.now(UTC),
            approved_by=protocol.approved_by,
        )
        session.add(row)
        await session.flush()
        op.details = {**op.details, "extraction_schema_id": str(row.id)}
        research.event(
            session, op.project_id, "EXTRACTION_SCHEMA_CREATED", schema_id=str(row.id), version=1
        )
        return str(row.id)


@activity.defn
async def prepare_extraction_batch(operation_id: str) -> list[str]:
    """Studies still awaiting an extraction attempt in this operation."""
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        attempted = set(cast(list[str], op.details.get("attempted", [])))
        batch_size = int(str(op.details["batch_size"]))
        pending = [
            study_id
            for study_id in cast(list[str], op.details["study_ids"])
            if study_id not in attempted
        ]
        return pending[:batch_size]


async def _study_passages(
    session: AsyncSession, study: Study, fields: list[SchemaField]
) -> list[ExtractionPassage]:
    """Passages from every report of the study, retrieved per field.

    One study may be reported by several publications, so evidence can come from
    any of them, and each passage keeps the work it came from.
    """
    collected: dict[tuple[uuid.UUID, int], ExtractionPassage] = {}
    counter = 0
    for link in await works_for_study(session, study.id):
        document = await latest_parsed_document(session, link.work_id)
        if document is None:
            continue
        chunks = await chunks_for(session, document.id)
        chunk_ids = {chunk.chunk_index: chunk.id for chunk in chunks}
        for field in fields:
            for passage in select_passages(
                chunks,
                field.queries(),
                limit=PASSAGES_PER_FIELD,
                prefer_sections=("METHODS", "RESULTS", "ABSTRACT"),
            ):
                key = (link.work_id, passage.chunk_index)
                if key in collected:
                    continue
                counter += 1
                collected[key] = ExtractionPassage(
                    passage_id=counter,
                    work_id=link.work_id,
                    parsed_document_id=document.id,
                    chunk_id=chunk_ids[passage.chunk_index],
                    page_start=passage.page_start,
                    page_end=passage.page_end,
                    section_path=passage.section_path,
                    section_type=passage.section_type,
                    text=passage.text,
                )
    ordered = sorted(collected.values(), key=lambda p: (str(p.work_id), p.page_start))
    return ordered[:MAX_PASSAGES]


def _persist_field(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    study: Study,
    schema_id: uuid.UUID,
    spec: SchemaField,
    value: Any,
    value_type: EvidenceValueType,
    unit: str | None,
    derivation: str | None,
    confidence: float | None,
    notes: str | None,
    agent_run_id: uuid.UUID | None,
    work_id: uuid.UUID | None = None,
) -> Evidence:
    evidence = Evidence(
        project_id=project_id,
        study_id=study.id,
        work_id=work_id,
        extraction_schema_id=schema_id,
        evidence_type=spec.evidence_type,
        field_name=spec.name,
        value_json=value,
        unit=unit or spec.unit,
        value_type=value_type,
        derivation=derivation,
        confidence=confidence,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
        status=EvidenceStatus.CURRENT,
        extractor_run_id=agent_run_id,
        notes=notes,
    )
    session.add(evidence)
    return evidence


@activity.defn
async def extract_evidence_batch(operation_id: str, study_ids: list[str]) -> dict[str, int]:
    counts = {"extracted": 0, "missing": 0, "uncertain": 0, "studies": 0}
    for study_id in study_ids:
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            study = await session.get(Study, uuid.UUID(study_id))
            if study is None or study.project_id != op.project_id:
                raise ApplicationError("Study is not part of this project", non_retryable=True)
            attempted = cast(list[str], op.details.get("attempted", []))
            op.details = {**op.details, "attempted": [*attempted, study_id]}

            schema_id = uuid.UUID(str(op.details["extraction_schema_id"]))
            schema_row = await session.get(ExtractionSchema, schema_id)
            assert schema_row is not None
            definition = ExtractionSchemaDefinition.model_validate(schema_row.schema_json)
            specs = definition.by_name()

            existing = await session.scalar(
                select(Evidence.id)
                .where(
                    Evidence.study_id == study.id,
                    Evidence.extraction_schema_id == schema_id,
                    Evidence.status == EvidenceStatus.CURRENT,
                )
                .limit(1)
            )
            if existing is not None:
                continue

            passages = await _study_passages(session, study, definition.fields)
            if not passages:
                # No parsed text means nothing to extract; that is recorded, not invented.
                research.event(
                    session,
                    op.project_id,
                    "EVIDENCE_EXTRACTION_SKIPPED",
                    study_id=study_id,
                    reason="No parsed full text for any report of this study",
                )
                continue

            payload = ExtractionInput(
                study_id=study.id,
                study_label=study.study_label,
                research_question=op.details.get("research_question") or study.title,  # type: ignore[arg-type]
                fields=[
                    ExtractionField(
                        name=field.name,
                        label=field.label,
                        kind=field.kind,
                        evidence_type=field.evidence_type,
                        unit=field.unit,
                        description=field.description,
                    )
                    for field in definition.fields
                ],
                passages=passages,
            )
            result = await run_agent(
                session,
                extraction_registry(),
                ContextBuilder(ToolRegistry(), research.gateway()),
                name="evidence_extractor",
                version="1",
                project_id=op.project_id,
                task=AgentTask(
                    task_type="evidence_extractor", payload=payload.model_dump(mode="json")
                ),
                workflow_id=op.temporal_workflow_id,
            )
            if result.status != AgentRunStatus.SUCCESS or not isinstance(
                result.structured_output, ExtractionOutput
            ):
                raise ApplicationError(
                    f"Extraction failed for study {study.study_label}; "
                    "evidence already persisted is preserved"
                )

            output = result.structured_output
            by_passage = {p.passage_id: p for p in passages}

            old_rows = list(
                await session.scalars(
                    select(Evidence).where(
                        Evidence.study_id == study.id, Evidence.status == EvidenceStatus.CURRENT
                    )
                )
            )
            for old in old_rows:
                old.status = EvidenceStatus.SUPERSEDED

            for field in output.extracted_fields:
                spec = specs[field.field_name]
                first = field.source_locations[0]
                evidence = _persist_field(
                    session,
                    project_id=op.project_id,
                    study=study,
                    schema_id=schema_id,
                    spec=spec,
                    value=field.value,
                    value_type=EvidenceValueType(field.value_type),
                    unit=field.unit,
                    derivation=field.derivation,
                    confidence=field.confidence,
                    notes=None,
                    agent_run_id=result.agent_run_id,
                    work_id=by_passage[first.passage_id].work_id,
                )
                await session.flush()
                for old in old_rows:
                    if old.field_name == field.field_name:
                        old.superseded_by = evidence.id
                for location in field.source_locations:
                    passage = by_passage[location.passage_id]
                    offset = passage.text.find(location.quote)
                    session.add(
                        EvidenceProvenance(
                            evidence_id=evidence.id,
                            parsed_document_id=passage.parsed_document_id,
                            chunk_id=passage.chunk_id,
                            work_id=passage.work_id,
                            page=location.page,
                            section=passage.section_path,
                            quote_start=offset if offset >= 0 else None,
                            quote_end=offset + len(location.quote) if offset >= 0 else None,
                            evidence_text=location.quote,
                        )
                    )
                counts["extracted"] += 1

            for missing in output.missing_fields:
                spec = specs[missing.field_name]
                evidence = _persist_field(
                    session,
                    project_id=op.project_id,
                    study=study,
                    schema_id=schema_id,
                    spec=spec,
                    value=None,
                    value_type=EvidenceValueType.MISSING,
                    unit=None,
                    derivation=None,
                    confidence=None,
                    notes=missing.reason,
                    agent_run_id=result.agent_run_id,
                )
                await session.flush()
                for old in old_rows:
                    if old.field_name == missing.field_name:
                        old.superseded_by = evidence.id
                counts["missing"] += 1

            for uncertain in output.uncertain_fields:
                spec = specs[uncertain.field_name]
                evidence = _persist_field(
                    session,
                    project_id=op.project_id,
                    study=study,
                    schema_id=schema_id,
                    spec=spec,
                    value=uncertain.candidate_value,
                    value_type=EvidenceValueType.MISSING
                    if uncertain.candidate_value is None
                    else EvidenceValueType.REPORTED,
                    unit=None,
                    derivation=None,
                    confidence=None,
                    notes=uncertain.reason,
                    agent_run_id=result.agent_run_id,
                )
                evidence.verification_status = EvidenceVerificationStatus.CONFLICT
                await session.flush()
                for old in old_rows:
                    if old.field_name == uncertain.field_name:
                        old.superseded_by = evidence.id
                for location in uncertain.source_locations:
                    passage = by_passage[location.passage_id]
                    session.add(
                        EvidenceProvenance(
                            evidence_id=evidence.id,
                            work_id=passage.work_id,
                            page=location.page,
                            section=passage.section_path,
                            evidence_text=location.quote,
                        )
                    )
                counts["uncertain"] += 1

            counts["studies"] += 1
            research.event(
                session,
                op.project_id,
                "EVIDENCE_EXTRACTED",
                study_id=study_id,
                extracted=len(output.extracted_fields),
                missing=len(output.missing_fields),
                uncertain=len(output.uncertain_fields),
                agent_run_id=str(result.agent_run_id),
            )
    return counts


@activity.defn
async def calculate_extraction_progress(operation_id: str) -> dict[str, int]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        study_ids = [uuid.UUID(raw) for raw in cast(list[str], op.details["study_ids"])]
        rows = list(
            await session.scalars(
                select(Evidence).where(
                    Evidence.project_id == op.project_id,
                    Evidence.status == EvidenceStatus.CURRENT,
                )
            )
        )
        with_evidence = {row.study_id for row in rows if row.study_id in set(study_ids)}
        counts = {
            "studies_total": len(study_ids),
            "studies_extracted": len(with_evidence),
            "studies_remaining": len(study_ids) - len(with_evidence),
            "evidence_items": len([r for r in rows if r.study_id in set(study_ids)]),
            "missing_values": len(
                [
                    r
                    for r in rows
                    if r.study_id in set(study_ids) and r.value_type == EvidenceValueType.MISSING
                ]
            ),
        }
        op.details = {**op.details, "progress": counts}
        return counts


@activity.defn
async def resolve_extraction_corpus(operation_id: str) -> list[str]:
    """Studies eligible for extraction: those whose reports reached a FULL_TEXT
    INCLUDE. A title/abstract INCLUDE is never sufficient."""
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        protocol = await latest_protocol(session, op.project_id)
        if protocol is None:
            raise ApplicationError("An approved protocol is required", non_retryable=True)
        included = set(await final_included_work_ids(session, protocol.id))
        studies = list(
            await session.scalars(select(Study).where(Study.project_id == op.project_id))
        )
        eligible = []
        for study in studies:
            if study.status.value == "MERGED":
                continue
            works = {link.work_id for link in await works_for_study(session, study.id)}
            if works & included:
                eligible.append(str(study.id))
        op.details = {
            **op.details,
            "study_ids": eligible,
            "research_question": protocol.research_question,
        }
        return eligible

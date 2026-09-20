"""Full-text screening: the stage whose INCLUDE actually means final inclusion.

Two rules shape this module. Availability is a retrieval fact, so a record with
no parsed full text is settled by the SYSTEM with FULL_TEXT_UNAVAILABLE and the
agent is never asked to guess. And the agent sees retrieved passages with their
page and section, never a whole document dump.
"""

import uuid
from typing import cast

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.runtime import run_agent
from ranah_agents.screening import (
    RetrievedPassage,
    ScreeningInput,
    ScreeningOutput,
    screening_registry,
)
from ranah_agents.tools import ToolRegistry
from ranah_documents.retrieval import select_passages
from ranah_domain.db import session_scope
from ranah_domain.enums import AgentRunStatus, FullTextAcquisitionStatus
from ranah_domain.models.screening import ReviewProtocol, ScreeningDecision
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_domain.repositories.fulltext import (
    acquisition_for,
    chunks_for,
    latest_parsed_document,
)
from ranah_domain.repositories.screening import criteria_for, effective_decisions, progress
from ranah_domain.schemas.screening import evaluate
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research

STAGE = "FULL_TEXT"
MAX_PASSAGES = 8
PREFERRED_SECTIONS = ("ABSTRACT", "METHODS", "RESULTS")


@activity.defn
async def prepare_full_text_batch(operation_id: str) -> list[str]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        protocol_id = uuid.UUID(str(op.details["protocol_id"]))
        decided = await effective_decisions(session, protocol_id, stage=STAGE)
        return [
            raw for raw in cast(list[str], op.details["work_ids"]) if uuid.UUID(raw) not in decided
        ][: int(str(op.details["batch_size"]))]


@activity.defn
async def screen_full_text_batch(operation_id: str, work_ids: list[str]) -> None:
    for work_id in work_ids:
        failed = False
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            protocol_id = uuid.UUID(str(op.details["protocol_id"]))
            work_uuid = uuid.UUID(work_id)
            if work_uuid in await effective_decisions(session, protocol_id, stage=STAGE):
                continue
            protocol = await session.get(ReviewProtocol, protocol_id)
            work = await session.get(WorkRecord, work_uuid)
            if not protocol or not work or work.project_id != op.project_id:
                raise ApplicationError("Invalid screening inputs", non_retryable=True)

            document = await latest_parsed_document(session, work_uuid)
            acquisition = await acquisition_for(session, op.project_id, work_uuid)
            if document is None:
                status = (
                    acquisition.status if acquisition else FullTextAcquisitionStatus.NOT_REQUESTED
                )
                session.add(
                    ScreeningDecision(
                        project_id=op.project_id,
                        work_id=work_uuid,
                        protocol_id=protocol_id,
                        protocol_version=protocol.version,
                        round_id=op.id,
                        stage=STAGE,
                        decision="EXCLUDE",
                        reason_code="FULL_TEXT_UNAVAILABLE",
                        rationale=(
                            "No parsed full text is on file for this record. "
                            f"Acquisition outcome: {status.value}."
                        ),
                        reviewer_type="SYSTEM",
                        criterion_assessments=[],
                        evidence_spans=[],
                    )
                )
                research.event(
                    session,
                    op.project_id,
                    "FULL_TEXT_SCREENING_UNAVAILABLE",
                    work_id=work_id,
                    acquisition_status=status.value,
                )
                continue

            criteria = await criteria_for(session, protocol_id)
            chunks = await chunks_for(session, document.id)
            queries = [protocol.research_question, *(str(c.value) for c in criteria)]
            passages = select_passages(
                chunks,
                queries,
                limit=MAX_PASSAGES,
                prefer_sections=PREFERRED_SECTIONS,
            )
            if not passages:
                passages = select_passages(
                    chunks, [work.title], limit=MAX_PASSAGES, prefer_sections=PREFERRED_SECTIONS
                )
            if not passages:
                raise ApplicationError(
                    "Parsed document yielded no retrievable passages", non_retryable=True
                )

            metadata = {
                field: getattr(work, field)
                for field in ("publication_year", "language", "publication_type")
            }
            observations = list(
                await session.scalars(
                    select(WorkMetadataObservation).where(
                        WorkMetadataObservation.work_id == work_uuid
                    )
                )
            )
            trusted: set[str] = set()
            for field, value in metadata.items():
                for_field = [
                    o
                    for o in observations
                    if o.field_name == field and o.field_value.get("value") is not None
                ]
                if (
                    value is not None
                    and len({o.provider for o in for_field}) >= 2
                    and all(o.field_value.get("value") == value for o in for_field)
                ):
                    trusted.add(field)

            payload = ScreeningInput(
                work_id=work_uuid,
                title=work.title,
                abstract=work.abstract,
                publication_year=work.publication_year,
                language=work.language,
                publication_type=work.publication_type,
                protocol_id=protocol_id,
                protocol_version=protocol.version,
                research_question=protocol.research_question,
                eligibility_criteria=criteria,
                deterministic_assessments=[evaluate(c, metadata, trusted) for c in criteria],
                stage="FULL_TEXT",
                passages=[
                    RetrievedPassage(
                        page_start=passage.page_start,
                        page_end=passage.page_end,
                        section_path=passage.section_path,
                        section_type=passage.section_type,
                        text=passage.text,
                    )
                    for passage in passages
                ],
            )
            result = await run_agent(
                session,
                screening_registry(),
                ContextBuilder(ToolRegistry(), research.gateway()),
                name="screening_agent",
                version="2",
                project_id=op.project_id,
                task=AgentTask(
                    task_type="screening_agent_full_text", payload=payload.model_dump(mode="json")
                ),
                workflow_id=op.temporal_workflow_id,
            )
            if result.status != AgentRunStatus.SUCCESS or not isinstance(
                result.structured_output, ScreeningOutput
            ):
                failed = True
            else:
                session.add(
                    ScreeningDecision(
                        project_id=op.project_id,
                        work_id=work_uuid,
                        protocol_id=protocol_id,
                        protocol_version=protocol.version,
                        round_id=op.id,
                        stage=STAGE,
                        reviewer_type="AI",
                        agent_run_id=result.agent_run_id,
                        **result.structured_output.model_dump(mode="json"),
                    )
                )
                research.event(
                    session,
                    op.project_id,
                    "FULL_TEXT_SCREENING_DECISION",
                    work_id=work_id,
                    decision=result.structured_output.decision,
                    pages=[p.page_start for p in passages],
                    agent_run_id=str(result.agent_run_id),
                )
        if failed:
            raise ApplicationError("Full-text screening failed; persisted decisions are preserved")


@activity.defn
async def calculate_full_text_progress(operation_id: str) -> dict[str, int]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        counts = await progress(
            session,
            uuid.UUID(str(op.details["protocol_id"])),
            [uuid.UUID(raw) for raw in cast(list[str], op.details["work_ids"])],
            stage=STAGE,
        )
        op.details = {**op.details, "progress": counts}
        return counts

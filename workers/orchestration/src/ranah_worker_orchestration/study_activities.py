"""Study linking: deterministic signals first, agent only for real ambiguity.

Order matters. A shared trial registration links without an LLM call. Weaker
signals become candidates the StudyLinker judges, and anything it cannot settle
is persisted as UNCERTAIN for a human. Nothing here deletes a publication.
"""

import uuid
from typing import cast

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.runtime import run_agent
from ranah_agents.studies import LinkCandidate, StudyLinkInput, StudyLinkOutput, study_registry
from ranah_agents.tools import ToolRegistry
from ranah_domain.db import session_scope
from ranah_domain.enums import (
    AgentRunStatus,
    StudyLinkDecisionType,
    StudyStatus,
    StudyWorkRelationship,
)
from ranah_domain.models.study import Study, StudyLinkDecision
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_domain.repositories.fulltext import chunks_for, latest_parsed_document
from ranah_domain.repositories.screening import latest_protocol
from ranah_domain.repositories.study import (
    attach_work,
    create_study,
    detach_work,
    study_for_work,
)
from ranah_literature.study_linking import (
    LinkTier,
    StudyCandidate,
    find_link_signals,
    find_registrations,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research

MAX_EXCERPTS = 6


async def _authors(session: AsyncSession, work_id: uuid.UUID) -> tuple[str, ...]:
    observations = await session.scalars(
        select(WorkMetadataObservation)
        .where(
            WorkMetadataObservation.work_id == work_id,
            WorkMetadataObservation.field_name == "authors",
        )
        .order_by(WorkMetadataObservation.observed_at.desc())
    )
    for observation in observations:
        value = observation.field_value.get("value")
        if isinstance(value, list) and value:
            return tuple(str(name) for name in value)
    return ()


async def _excerpts(session: AsyncSession, work_id: uuid.UUID) -> list[str]:
    """Identity-bearing passages only: methods/front matter, never the whole paper."""
    document = await latest_parsed_document(session, work_id)
    if document is None:
        return []
    chunks = await chunks_for(session, document.id)
    wanted = [
        chunk
        for chunk in chunks
        if chunk.section_type in ("METHODS", "ABSTRACT", "FRONT_MATTER", "OTHER")
    ]
    return [chunk.text for chunk in wanted[:MAX_EXCERPTS]]


async def _candidate(session: AsyncSession, work: WorkRecord) -> StudyCandidate:
    return StudyCandidate(
        work_id=str(work.id),
        title=work.title,
        abstract=work.abstract,
        full_text="\n".join(await _excerpts(session, work.id)) or None,
        authors=await _authors(session, work.id),
        publication_year=work.publication_year,
        publication_type=work.publication_type,
    )


def _record_decision(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    work_id: uuid.UUID,
    candidate_work_id: uuid.UUID | None,
    study_id: uuid.UUID | None,
    decision: StudyLinkDecisionType,
    relationship_type: StudyWorkRelationship | None,
    confidence: float | None,
    signals: dict[str, object],
    evidence: list[str],
    rationale: str,
    decided_by: str,
    agent_run_id: uuid.UUID | None = None,
) -> None:
    session.add(
        StudyLinkDecision(
            project_id=project_id,
            work_id=work_id,
            candidate_work_id=candidate_work_id,
            study_id=study_id,
            decision=decision,
            relationship_type=relationship_type,
            confidence=confidence,
            signals=signals,
            evidence=evidence,
            rationale=rationale,
            decided_by=decided_by,
            agent_run_id=agent_run_id,
        )
    )


@activity.defn
async def link_studies(operation_id: str) -> dict[str, int]:
    """One pass over the operation's works: deterministic links, then agent
    adjudication of the remaining candidates."""
    counts = {"studies": 0, "linked": 0, "separate": 0, "needs_review": 0}
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        work_ids = [uuid.UUID(raw) for raw in cast(list[str], op.details["work_ids"])]
        works = []
        for work_id in work_ids:
            work = await session.get(WorkRecord, work_id)
            if work is not None and work.project_id == op.project_id:
                works.append(work)
        candidates = [await _candidate(session, work) for work in works]
        by_id = {str(work.id): work for work in works}
        signals = find_link_signals(candidates)
        protocol = await latest_protocol(session, op.project_id)
        question = protocol.research_question if protocol else "Not specified"

        # Every work starts as its own study; linking then merges reports.
        for work in works:
            if await study_for_work(session, op.project_id, work.id) is None:
                registrations = sorted(
                    find_registrations(
                        next(c.searchable() for c in candidates if c.work_id == str(work.id))
                    )
                )
                await create_study(
                    session,
                    op.project_id,
                    work,
                    registration_id=registrations[0] if registrations else None,
                )
                counts["studies"] += 1

        agent_pairs: list[tuple[StudyCandidate, StudyCandidate, dict[str, object], LinkTier]] = []
        for signal in signals:
            left, right = by_id[signal.work_id_a], by_id[signal.work_id_b]
            left_study = await study_for_work(session, op.project_id, left.id)
            right_study = await study_for_work(session, op.project_id, right.id)
            if left_study is None or right_study is None or left_study.id == right_study.id:
                continue
            if signal.tier is LinkTier.REGISTRATION:
                await _merge(
                    session,
                    op.project_id,
                    keep=left_study,
                    absorbed=right_study,
                    work_id=right.id,
                    relationship_type=StudyWorkRelationship.SECONDARY_REPORT,
                    confidence=1.0,
                    signals=signal.signals,
                    evidence=list(signal.evidence),
                    rationale="Both reports state the same trial registration identifier",
                    decided_by="SYSTEM",
                    origin_work_id=left.id,
                )
                counts["linked"] += 1
                continue
            agent_pairs.append(
                (
                    next(c for c in candidates if c.work_id == str(left.id)),
                    next(c for c in candidates if c.work_id == str(right.id)),
                    dict(signal.signals),
                    signal.tier,
                )
            )

        for left_candidate, right_candidate, detail, _tier in agent_pairs:
            left = by_id[left_candidate.work_id]
            right = by_id[right_candidate.work_id]
            left_study = await study_for_work(session, op.project_id, left.id)
            right_study = await study_for_work(session, op.project_id, right.id)
            if left_study is None or right_study is None or left_study.id == right_study.id:
                continue
            payload = StudyLinkInput(
                project_id=op.project_id,
                research_question=question,
                left=_link_candidate(left_candidate, left),
                right=_link_candidate(right_candidate, right),
                deterministic_signals=detail,
            )
            result = await run_agent(
                session,
                study_registry(),
                ContextBuilder(ToolRegistry(), research.gateway()),
                name="study_linker",
                version="1",
                project_id=op.project_id,
                task=AgentTask(task_type="study_linker", payload=payload.model_dump(mode="json")),
                workflow_id=op.temporal_workflow_id,
            )
            output = result.structured_output
            if not isinstance(output, StudyLinkOutput) or result.status not in (
                AgentRunStatus.SUCCESS,
                AgentRunStatus.NEEDS_HUMAN,
            ):
                _record_decision(
                    session,
                    op.project_id,
                    work_id=right.id,
                    candidate_work_id=left.id,
                    study_id=None,
                    decision=StudyLinkDecisionType.UNCERTAIN,
                    relationship_type=None,
                    confidence=None,
                    signals=detail,
                    evidence=[],
                    rationale="The study linker produced no usable judgement",
                    decided_by="AI",
                    agent_run_id=result.agent_run_id,
                )
                right_study.status = StudyStatus.NEEDS_REVIEW
                counts["needs_review"] += 1
                continue

            if output.same_study and not output.requires_human:
                await _merge(
                    session,
                    op.project_id,
                    keep=left_study,
                    absorbed=right_study,
                    work_id=right.id,
                    relationship_type=output.relationship_type
                    or StudyWorkRelationship.SECONDARY_REPORT,
                    confidence=output.confidence,
                    signals=detail,
                    evidence=list(output.evidence),
                    rationale=output.rationale,
                    decided_by="AI",
                    origin_work_id=left.id,
                    agent_run_id=result.agent_run_id,
                )
                counts["linked"] += 1
            else:
                decision = (
                    StudyLinkDecisionType.UNCERTAIN
                    if output.requires_human
                    else StudyLinkDecisionType.KEEP_SEPARATE
                )
                _record_decision(
                    session,
                    op.project_id,
                    work_id=right.id,
                    candidate_work_id=left.id,
                    study_id=right_study.id,
                    decision=decision,
                    relationship_type=None,
                    confidence=output.confidence,
                    signals=detail,
                    evidence=list(output.evidence),
                    rationale=output.rationale,
                    decided_by="AI",
                    agent_run_id=result.agent_run_id,
                )
                if decision is StudyLinkDecisionType.UNCERTAIN:
                    right_study.status = StudyStatus.NEEDS_REVIEW
                    counts["needs_review"] += 1
                else:
                    counts["separate"] += 1

        op.details = {**op.details, "progress": counts}
        research.event(session, op.project_id, "STUDY_LINKING_COMPLETED", **counts)
    return counts


def _link_candidate(candidate: StudyCandidate, work: WorkRecord) -> LinkCandidate:
    return LinkCandidate(
        work_id=work.id,
        title=candidate.title,
        abstract=candidate.abstract,
        authors=list(candidate.authors),
        publication_year=candidate.publication_year,
        publication_type=candidate.publication_type,
        registration_ids=sorted(find_registrations(candidate.searchable())),
        full_text_excerpts=[candidate.full_text] if candidate.full_text else [],
    )


async def _merge(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    keep: Study,
    absorbed: Study,
    work_id: uuid.UUID,
    relationship_type: StudyWorkRelationship,
    confidence: float | None,
    signals: dict[str, object],
    evidence: list[str],
    rationale: str,
    decided_by: str,
    origin_work_id: uuid.UUID,
    agent_run_id: uuid.UUID | None = None,
) -> None:
    """Move the report onto the kept study. The publication records themselves
    are untouched; only the study grouping changes. The absorbed study is
    superseded, never deleted, so its link history keeps a referent."""
    await detach_work(session, absorbed.id, work_id)
    absorbed.status = StudyStatus.MERGED
    absorbed.superseded_by = keep.id
    await session.flush()
    await attach_work(
        session,
        keep,
        work_id,
        relationship_type=relationship_type,
        confidence=confidence,
        linked_by=f"{decided_by.lower()}:study_linker_v1",
        agent_run_id=agent_run_id,
    )
    if keep.registration_id is None and isinstance(signals.get("registration_id"), str):
        keep.registration_id = cast(str, signals["registration_id"])
    _record_decision(
        session,
        project_id,
        work_id=work_id,
        candidate_work_id=origin_work_id,
        study_id=keep.id,
        decision=StudyLinkDecisionType.LINK,
        relationship_type=relationship_type,
        confidence=confidence,
        signals=signals,
        evidence=evidence,
        rationale=rationale,
        decided_by=decided_by,
        agent_run_id=agent_run_id,
    )


@activity.defn
async def calculate_study_progress(operation_id: str) -> dict[str, int]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        studies = list(
            await session.scalars(select(Study).where(Study.project_id == op.project_id))
        )
        counts = {
            "studies": len(studies),
            "needs_review": sum(s.status == StudyStatus.NEEDS_REVIEW for s in studies),
            "with_registration": sum(bool(s.registration_id) for s in studies),
        }
        op.details = {**op.details, "progress": counts}
        return counts

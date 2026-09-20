import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.models.dedupe import DuplicateDecision, DuplicateGroup, DuplicateMember
from ranah_domain.models.project import ResearchFramework
from ranah_domain.models.screening import EligibilityCriterion, ReviewProtocol, ScreeningDecision
from ranah_domain.models.work import WorkRecord
from ranah_domain.schemas.screening import BoundCriterion


async def latest_protocol(session: AsyncSession, project_id: uuid.UUID) -> ReviewProtocol | None:
    return cast(
        ReviewProtocol | None,
        await session.scalar(
            select(ReviewProtocol)
            .where(ReviewProtocol.project_id == project_id)
            .order_by(ReviewProtocol.version.desc())
            .limit(1)
        ),
    )


async def criteria_for(session: AsyncSession, protocol_id: uuid.UUID) -> list[BoundCriterion]:
    rows = await session.scalars(
        select(EligibilityCriterion)
        .where(EligibilityCriterion.protocol_id == protocol_id)
        .order_by(EligibilityCriterion.priority, EligibilityCriterion.id)
    )
    return [BoundCriterion.model_validate(row) for row in rows]


async def canonical_ids(session: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    ids = list(
        await session.scalars(
            select(WorkRecord.id).where(WorkRecord.project_id == project_id).order_by(WorkRecord.id)
        )
    )
    decisions = await session.scalars(
        select(DuplicateDecision)
        .join(DuplicateGroup)
        .where(DuplicateGroup.project_id == project_id)
        .order_by(DuplicateDecision.created_at, DuplicateDecision.id)
    )
    latest = {d.duplicate_group_id: d for d in decisions}
    removed: set[uuid.UUID] = set()
    for group, decision in latest.items():
        if decision.decision == "MERGE" and decision.canonical_work_id:
            removed.update(
                await session.scalars(
                    select(DuplicateMember.work_id).where(
                        DuplicateMember.duplicate_group_id == group,
                        DuplicateMember.work_id != decision.canonical_work_id,
                    )
                )
            )
    return [work_id for work_id in ids if work_id not in removed]


async def effective_decisions(
    session: AsyncSession, protocol_id: uuid.UUID, *, stage: str = "TITLE_ABSTRACT"
) -> dict[uuid.UUID, ScreeningDecision]:
    """Latest decision per work for one protocol and stage, with a human
    decision always outranking an AI or system one."""
    rows = await session.scalars(
        select(ScreeningDecision)
        .where(
            ScreeningDecision.protocol_id == protocol_id,
            ScreeningDecision.stage == stage,
        )
        .order_by(ScreeningDecision.created_at, ScreeningDecision.id)
    )
    effective: dict[uuid.UUID, ScreeningDecision] = {}
    for row in rows:
        previous = effective.get(row.work_id)
        if row.reviewer_type == "HUMAN" or previous is None or previous.reviewer_type != "HUMAN":
            effective[row.work_id] = row
    return effective


async def progress(
    session: AsyncSession,
    protocol_id: uuid.UUID,
    work_ids: list[uuid.UUID],
    *,
    stage: str = "TITLE_ABSTRACT",
) -> dict[str, int]:
    effective = await effective_decisions(session, protocol_id, stage=stage)
    rows = [effective[key] for key in work_ids if key in effective]
    return {
        "total": len(work_ids),
        "screened": len(rows),
        "remaining": len(work_ids) - len(rows),
        **{
            decision.lower(): sum(row.decision == decision for row in rows)
            for decision in ("INCLUDE", "EXCLUDE", "UNCERTAIN", "CONFLICT")
        },
    }


async def final_included_work_ids(session: AsyncSession, protocol_id: uuid.UUID) -> list[uuid.UUID]:
    """Invariant 3/4: final inclusion comes only from the latest effective
    FULL_TEXT decision. A title/abstract INCLUDE never qualifies a record for
    evidence extraction (docs/DATA_MODEL.md #103)."""
    effective = await effective_decisions(session, protocol_id, stage="FULL_TEXT")
    return sorted(
        (work_id for work_id, decision in effective.items() if decision.decision == "INCLUDE"),
        key=str,
    )


def decision_view(row: ScreeningDecision) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def protocol_view(session: AsyncSession, row: ReviewProtocol) -> dict[str, Any]:
    framework = await session.get(ResearchFramework, row.framework_id)
    return {
        **{column.name: getattr(row, column.name) for column in row.__table__.columns},
        "eligibility_criteria": [
            c.model_dump(mode="json") for c in await criteria_for(session, row.id)
        ],
        "framework": framework.structured_elements if framework else None,
    }

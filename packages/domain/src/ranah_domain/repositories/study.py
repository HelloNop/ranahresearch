import uuid
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.enums import StudyStatus, StudyType, StudyWorkRelationship
from ranah_domain.models.study import Study, StudyLinkDecision, StudyWork
from ranah_domain.models.work import WorkRecord


async def next_label(session: AsyncSession, project_id: uuid.UUID) -> str:
    """S01, S02, ... Display-only; identity is the UUID (docs/DATA_MODEL.md #3)."""
    used = await session.scalar(
        select(func.count()).select_from(Study).where(Study.project_id == project_id)
    )
    return f"S{(used or 0) + 1:02d}"


async def study_for_work(
    session: AsyncSession, project_id: uuid.UUID, work_id: uuid.UUID
) -> Study | None:
    return cast(
        Study | None,
        await session.scalar(
            select(Study)
            .join(StudyWork, StudyWork.study_id == Study.id)
            .where(Study.project_id == project_id, StudyWork.work_id == work_id)
            .limit(1)
        ),
    )


async def works_for_study(session: AsyncSession, study_id: uuid.UUID) -> list[StudyWork]:
    rows = await session.scalars(
        select(StudyWork).where(StudyWork.study_id == study_id).order_by(StudyWork.created_at)
    )
    return list(rows)


async def create_study(
    session: AsyncSession,
    project_id: uuid.UUID,
    work: WorkRecord,
    *,
    registration_id: str | None = None,
    study_type: StudyType = StudyType.OTHER,
    linked_by: str = "system:study_linking_v1",
) -> Study:
    """A work with no known sibling still gets its own study; one report is a
    study of one report, not an absence of a study."""
    study = Study(
        project_id=project_id,
        study_label=await next_label(session, project_id),
        title=work.title,
        study_type=study_type,
        status=StudyStatus.CANDIDATE,
        registration_id=registration_id,
    )
    session.add(study)
    await session.flush()
    session.add(
        StudyWork(
            study_id=study.id,
            work_id=work.id,
            relationship_type=StudyWorkRelationship.PRIMARY_REPORT,
            confidence=1.0,
            linked_by=linked_by,
        )
    )
    await session.flush()
    return study


async def attach_work(
    session: AsyncSession,
    study: Study,
    work_id: uuid.UUID,
    *,
    relationship_type: StudyWorkRelationship,
    confidence: float | None,
    linked_by: str,
    agent_run_id: uuid.UUID | None = None,
) -> StudyWork | None:
    existing = await session.scalar(
        select(StudyWork).where(StudyWork.study_id == study.id, StudyWork.work_id == work_id)
    )
    if existing is not None:
        return None
    link = StudyWork(
        study_id=study.id,
        work_id=work_id,
        relationship_type=relationship_type,
        confidence=confidence,
        linked_by=linked_by,
        agent_run_id=agent_run_id,
    )
    session.add(link)
    await session.flush()
    return link


async def detach_work(session: AsyncSession, study_id: uuid.UUID, work_id: uuid.UUID) -> None:
    """Removes the grouping row only. The publication and the decision history
    that explains the move both remain."""
    link = await session.scalar(
        select(StudyWork).where(StudyWork.study_id == study_id, StudyWork.work_id == work_id)
    )
    if link is not None:
        await session.delete(link)
        await session.flush()


async def decisions_for_work(
    session: AsyncSession, project_id: uuid.UUID, work_id: uuid.UUID
) -> list[StudyLinkDecision]:
    rows = await session.scalars(
        select(StudyLinkDecision)
        .where(
            StudyLinkDecision.project_id == project_id,
            (StudyLinkDecision.work_id == work_id)
            | (StudyLinkDecision.candidate_work_id == work_id),
        )
        .order_by(StudyLinkDecision.created_at.desc(), StudyLinkDecision.id.desc())
    )
    return list(rows)


def decision_view(row: StudyLinkDecision) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


async def study_view(session: AsyncSession, study: Study) -> dict[str, Any]:
    links = await works_for_study(session, study.id)
    works = {}
    for link in links:
        work = await session.get(WorkRecord, link.work_id)
        if work is not None:
            works[link.work_id] = work
    return {
        **{column.name: getattr(study, column.name) for column in study.__table__.columns},
        "works": [
            {
                "work_id": link.work_id,
                "relationship_type": link.relationship_type,
                "confidence": link.confidence,
                "linked_by": link.linked_by,
                "title": works[link.work_id].title if link.work_id in works else None,
                "publication_year": works[link.work_id].publication_year
                if link.work_id in works
                else None,
                "doi": works[link.work_id].doi if link.work_id in works else None,
            }
            for link in links
        ],
    }


async def studies_for_project(session: AsyncSession, project_id: uuid.UUID) -> list[Study]:
    """Superseded studies stay on file for audit but are not part of the corpus."""
    rows = await session.scalars(
        select(Study)
        .where(Study.project_id == project_id, Study.status != StudyStatus.MERGED)
        .order_by(Study.study_label)
    )
    return list(rows)

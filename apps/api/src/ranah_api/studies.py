import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import Field
from ranah_domain.enums import (
    FullTextAcquisitionStatus,
    StudyLinkDecisionType,
    StudyStatus,
    StudyType,
    StudyWorkRelationship,
)
from ranah_domain.models.study import Study, StudyLinkDecision, StudyWork
from ranah_domain.repositories.fulltext import acquisition_statuses
from ranah_domain.repositories.screening import effective_decisions, latest_protocol
from ranah_domain.repositories.study import (
    attach_work,
    decision_view,
    decisions_for_work,
    detach_work,
    studies_for_project,
    study_for_work,
    study_view,
)
from ranah_domain.schemas.screening import StrictModel, Text
from sqlalchemy import select

from ranah_api.fulltext import scoped_work
from ranah_api.projects import (
    DB,
    Principal,
    append_event,
    error,
    scoped_project,
    start_operation,
)

router = APIRouter(prefix="/projects", tags=["Studies"])


class LinkDecision(StrictModel):
    work_id: uuid.UUID
    target_study_id: uuid.UUID | None = None
    decision: Literal["LINK", "KEEP_SEPARATE", "UNCERTAIN"]
    relationship_type: StudyWorkRelationship | None = None
    rationale: Text = Field(default="Human study-link review")


class StudyDesign(StrictModel):
    study_type: StudyType
    reason: Text


@router.post("/{project_id}/studies/{study_id}/design")
async def set_study_design(
    project_id: uuid.UUID, study_id: uuid.UUID, data: StudyDesign, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    study = await session.get(Study, study_id)
    if study is None or study.project_id != project_id:
        raise error(404, "NOT_FOUND", "Study not found in this project")
    if study.study_type != data.study_type:
        previous = study.study_type
        study.study_type = data.study_type
        append_event(
            session,
            project,
            user,
            "STUDY_DESIGN_CLASSIFIED",
            study_id=str(study_id),
            previous=previous.value,
            current=data.study_type.value,
            reason=data.reason,
        )
        await session.flush()
        await session.refresh(study)
    return await study_view(session, study)


@router.get("/{project_id}/studies")
async def list_studies(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    return [
        await study_view(session, study) for study in await studies_for_project(session, project_id)
    ]


@router.get("/{project_id}/studies/{study_id}")
async def get_study(
    project_id: uuid.UUID, study_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    await scoped_project(session, user, project_id)
    study = await session.get(Study, study_id)
    if study is None or study.project_id != project_id:
        raise error(404, "NOT_FOUND", "Study not found in this project")
    view = await study_view(session, study)
    history: list[dict[str, Any]] = []
    for link in view["works"]:
        history.extend(
            decision_view(row)
            for row in await decisions_for_work(session, project_id, link["work_id"])
        )
    return {**view, "link_history": history}


@router.post("/{project_id}/studies/build", status_code=202)
async def build_studies(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Group the title/abstract-included corpus into studies."""
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
        raise error(409, "WORKFLOW_CONFLICT", "No records passed title/abstract screening")
    return await start_operation(
        session,
        project,
        "studies",
        {"work_ids": work_ids, "records_total": len(work_ids)},
    )


@router.post("/{project_id}/studies/link", status_code=201)
async def human_link_decision(
    project_id: uuid.UUID, data: LinkDecision, session: DB, user: Principal
) -> Any:
    """A human decision appends history; it never rewrites the AI's record."""
    project = await scoped_project(session, user, project_id, write=True)
    await scoped_work(session, project_id, data.work_id)
    current = await study_for_work(session, project_id, data.work_id)
    if current is None:
        raise error(409, "WORKFLOW_CONFLICT", "Build studies before reviewing links")

    target: Study | None = None
    if data.decision == "LINK":
        if not data.target_study_id or not data.relationship_type:
            raise error(
                422, "USER_INPUT_ERROR", "Linking needs a target study and a relationship type"
            )
        target = await session.get(Study, data.target_study_id)
        if target is None or target.project_id != project_id:
            raise error(404, "NOT_FOUND", "Target study not found in this project")
        if target.id != current.id:
            await attach_work(
                session,
                target,
                data.work_id,
                relationship_type=data.relationship_type,
                confidence=None,
                linked_by=f"human:{user.id}",
            )
            # The work moves to the target study; its publication record is untouched.
            await detach_work(session, current.id, data.work_id)
            if not await session.scalar(
                select(StudyWork.id).where(StudyWork.study_id == current.id)
            ):
                current.status = StudyStatus.MERGED
                current.superseded_by = target.id
        target.status = StudyStatus.CONFIRMED
    elif data.decision == "KEEP_SEPARATE":
        current.status = StudyStatus.CONFIRMED
    else:
        current.status = StudyStatus.NEEDS_REVIEW

    row = StudyLinkDecision(
        project_id=project_id,
        work_id=data.work_id,
        candidate_work_id=None,
        study_id=target.id if target else current.id,
        decision=StudyLinkDecisionType(data.decision),
        relationship_type=data.relationship_type if data.decision == "LINK" else None,
        confidence=None,
        signals={},
        evidence=[],
        rationale=data.rationale,
        decided_by="HUMAN",
        reviewer_id=user.id,
    )
    session.add(row)
    await session.flush()
    append_event(
        session,
        project,
        user,
        "STUDY_LINK_HUMAN_DECISION",
        work_id=str(data.work_id),
        decision=data.decision,
    )
    return decision_view(row)


@router.get("/{project_id}/studies-overview")
async def studies_overview(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    """Study-level readiness for extraction, including full-text availability."""
    await scoped_project(session, user, project_id)
    statuses = await acquisition_statuses(session, project_id)
    studies = await studies_for_project(session, project_id)
    rows = []
    for study in studies:
        view = await study_view(session, study)
        availability = [
            statuses.get(link["work_id"], FullTextAcquisitionStatus.NOT_REQUESTED)
            for link in view["works"]
        ]
        rows.append(
            {
                "study_id": study.id,
                "study_label": study.study_label,
                "title": study.title,
                "status": study.status,
                "registration_id": study.registration_id,
                "work_count": len(view["works"]),
                "full_text_available": FullTextAcquisitionStatus.AVAILABLE in availability,
            }
        )
    return {
        "total": len(rows),
        "needs_review": sum(row["status"] == StudyStatus.NEEDS_REVIEW for row in rows),
        "with_full_text": sum(bool(row["full_text_available"]) for row in rows),
        "studies": rows,
    }

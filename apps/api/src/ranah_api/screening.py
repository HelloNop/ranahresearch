import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, Query
from pydantic import Field
from ranah_agents.screening import ProtocolOutput
from ranah_domain.enums import ProjectStatus, ResearchPlanStatus
from ranah_domain.models.project import ResearchFramework
from ranah_domain.models.screening import (
    EligibilityCriterion,
    ProtocolAmendment,
    ReviewProtocol,
    ScreeningDecision,
)
from ranah_domain.models.search import SearchRun
from ranah_domain.models.workflow import WorkflowRun
from ranah_domain.repositories.screening import (
    canonical_ids,
    criteria_for,
    decision_view,
    effective_decisions,
    latest_protocol,
    progress,
    protocol_view,
)
from ranah_domain.schemas.screening import ReasonCode, StrictModel, Text
from sqlalchemy import select

from ranah_api.projects import (
    DB,
    Principal,
    append_event,
    ensure_idle,
    error,
    latest_plan,
    scoped_project,
    start_operation,
)

router = APIRouter(prefix="/projects", tags=["Protocol and screening"])


class GenerateProtocol(StrictModel):
    user_constraints: str | None = Field(default=None, max_length=12000)


class Revision(StrictModel):
    protocol: ProtocolOutput
    reason: Text


class Approval(StrictModel):
    acknowledge_uncertainties: bool = False


class HumanDecision(StrictModel):
    round_id: uuid.UUID
    decision: Literal["INCLUDE", "EXCLUDE", "UNCERTAIN"]
    reason_code: ReasonCode | None = None
    note: str = Field(default="", max_length=12000)


@router.get("/{project_id}/protocol")
async def get_protocol(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    row = await latest_protocol(session, project_id)
    return await protocol_view(session, row) if row else None


@router.get("/{project_id}/protocol/versions")
async def versions(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    rows = await session.scalars(
        select(ReviewProtocol)
        .where(ReviewProtocol.project_id == project_id)
        .order_by(ReviewProtocol.version.desc())
    )
    return [await protocol_view(session, row) for row in rows]


@router.get("/{project_id}/eligibility-criteria")
async def eligibility(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    row = await latest_protocol(session, project_id)
    return await criteria_for(session, row.id) if row else []


@router.post("/{project_id}/protocol/generate", status_code=202)
async def generate(
    project_id: uuid.UUID, data: GenerateProtocol, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    plan = await latest_plan(session, project_id)
    if not plan or plan.status != ResearchPlanStatus.APPROVED:
        raise error(409, "WORKFLOW_CONFLICT", "Approve the research plan first")
    if await latest_protocol(session, project_id):
        raise error(409, "WORKFLOW_CONFLICT", "Revise the existing protocol to preserve amendments")
    framework = await session.scalar(
        select(ResearchFramework).where(ResearchFramework.research_plan_id == plan.id)
    )
    if not framework:
        raise error(409, "WORKFLOW_CONFLICT", "A research framework is required")
    project.status = ProjectStatus.PROTOCOL
    return await start_operation(
        session,
        project,
        "protocol",
        {
            "plan_id": str(plan.id),
            "framework_id": str(framework.id),
            "user_constraints": data.user_constraints,
        },
    )


async def current_protocol(
    project_id: uuid.UUID, protocol_id: uuid.UUID, session: DB
) -> ReviewProtocol:
    row = await latest_protocol(session, project_id)
    if row is None or row.id != protocol_id:
        raise error(409, "WORKFLOW_CONFLICT", "Use the current protocol version")
    return row


@router.post("/{project_id}/protocol/{protocol_id}/approve")
async def approve(
    project_id: uuid.UUID, protocol_id: uuid.UUID, data: Approval, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    await ensure_idle(session, project_id)
    row = await current_protocol(project_id, protocol_id, session)
    plan = await latest_plan(session, project_id)
    if not plan or plan.id != row.research_plan_id or plan.status != ResearchPlanStatus.APPROVED:
        raise error(
            409, "WORKFLOW_CONFLICT", "Protocol must match the current approved research plan"
        )
    if row.status != "PROPOSED":
        raise error(409, "WORKFLOW_CONFLICT", "Only a proposed protocol can be approved")
    if row.uncertainties and not data.acknowledge_uncertainties:
        raise error(
            409, "NEEDS_HUMAN", "Review and acknowledge protocol uncertainties before approval"
        )
    row.status, row.approved_at, row.approved_by = "APPROVED", datetime.now(UTC), user.id
    append_event(
        session, project, user, "PROTOCOL_APPROVED", protocol_id=str(row.id), version=row.version
    )
    return await protocol_view(session, row)


@router.post("/{project_id}/protocol/{protocol_id}/revise", status_code=201)
async def revise(
    project_id: uuid.UUID, protocol_id: uuid.UUID, data: Revision, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    await ensure_idle(session, project_id)
    old = await current_protocol(project_id, protocol_id, session)
    if old.status not in ("PROPOSED", "APPROVED"):
        raise error(409, "WORKFLOW_CONFLICT", "Only proposed or approved protocols may be revised")
    values = data.protocol.model_dump(mode="json")
    if values["review_type"] != old.review_type or set(values["information_sources"]) != set(
        old.information_sources
    ):
        raise error(
            422,
            "SCIENTIFIC_VALIDATION_ERROR",
            "Preserve review method and actual information sources",
        )
    criteria = values.pop("eligibility_criteria")
    new = ReviewProtocol(
        project_id=project_id,
        research_plan_id=old.research_plan_id,
        framework_id=old.framework_id,
        research_question=old.research_question,
        version=old.version + 1,
        status="PROPOSED",
        **values,
    )
    session.add(new)
    await session.flush()
    session.add_all([EligibilityCriterion(protocol_id=new.id, **c) for c in criteria])
    before = await protocol_view(session, old)
    changed = {**values, "eligibility_criteria": criteria}
    before["eligibility_criteria"] = [
        c.model_dump(mode="json", exclude={"id"}) for c in await criteria_for(session, old.id)
    ]
    screened = await session.scalar(
        select(ScreeningDecision.id).where(ScreeningDecision.project_id == project_id).limit(1)
    )
    searched = await session.scalar(
        select(SearchRun.id).where(SearchRun.project_id == project_id).limit(1)
    )
    for key, value in changed.items():
        if before[key] != value:
            session.add(
                ProtocolAmendment(
                    protocol_id=new.id,
                    from_version=old.version,
                    to_version=new.version,
                    field_path=key,
                    old_value=before[key],
                    new_value=value,
                    reason=data.reason,
                    created_by=user.id,
                    change_type="POST_SCREENING_AMENDMENT"
                    if screened
                    else ("POST_SEARCH_AMENDMENT" if searched else "PRE_SEARCH_CHANGE"),
                )
            )
    old.status = "SUPERSEDED"
    project.status = ProjectStatus.PROTOCOL
    append_event(
        session,
        project,
        user,
        "PROTOCOL_REVISED",
        protocol_id=str(new.id),
        from_version=old.version,
        reason=data.reason,
    )
    return await protocol_view(session, new)


@router.post("/{project_id}/screening/title-abstract/start", status_code=202)
async def start_screening(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    protocol = await latest_protocol(session, project_id)
    plan = await latest_plan(session, project_id)
    if (
        not protocol
        or protocol.status != "APPROVED"
        or not plan
        or plan.id != protocol.research_plan_id
        or plan.status != ResearchPlanStatus.APPROVED
    ):
        raise error(
            409, "WORKFLOW_CONFLICT", "Approve a protocol for the current research plan first"
        )
    work_ids = await canonical_ids(session, project_id)
    if not work_ids:
        raise error(409, "WORKFLOW_CONFLICT", "Discover canonical literature first")
    project.status = ProjectStatus.SCREENING
    return await start_operation(
        session,
        project,
        "screening",
        {
            "protocol_id": str(protocol.id),
            "protocol_version": protocol.version,
            "stage": "TITLE_ABSTRACT",
            "work_ids": list(map(str, work_ids)),
            "records_total": len(work_ids),
            "batch_size": max(1, min(100, int(os.environ.get("SCREENING_BATCH_SIZE", "10")))),
        },
    )


async def selected_round(
    project_id: uuid.UUID, session: DB, round_id: uuid.UUID | None = None
) -> WorkflowRun | None:
    stmt = select(WorkflowRun).where(
        WorkflowRun.project_id == project_id,
        WorkflowRun.workflow_type == "TitleAbstractScreeningWorkflow",
    )
    if round_id:
        stmt = stmt.where(WorkflowRun.id == round_id)
    return cast(
        WorkflowRun | None,
        await session.scalar(stmt.order_by(WorkflowRun.started_at.desc()).limit(1)),
    )


@router.get("/{project_id}/screening/title-abstract/progress")
async def get_progress(
    project_id: uuid.UUID, session: DB, user: Principal, round_id: uuid.UUID | None = None
) -> Any:
    await scoped_project(session, user, project_id)
    row = await selected_round(project_id, session, round_id)
    if not row:
        return None
    counts = await progress(
        session,
        uuid.UUID(str(row.details["protocol_id"])),
        [uuid.UUID(str(i)) for i in cast(list[str], row.details["work_ids"])],
    )
    return {
        "round_id": row.id,
        "protocol_version": row.details["protocol_version"],
        "protocol_id": row.details["protocol_id"],
        "stage": "TITLE_ABSTRACT",
        "status": row.status,
        "error": row.details.get("error"),
        **counts,
    }


@router.get("/{project_id}/screening/title-abstract")
async def queue(
    project_id: uuid.UUID,
    session: DB,
    user: Principal,
    round_id: uuid.UUID | None = None,
    filter: Literal[
        "ALL", "UNSCREENED", "INCLUDE", "EXCLUDE", "UNCERTAIN", "HUMAN_OVERRIDDEN"
    ] = "ALL",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> Any:
    await scoped_project(session, user, project_id)
    row = await selected_round(project_id, session, round_id)
    if not row:
        return []
    effective = await effective_decisions(session, uuid.UUID(str(row.details["protocol_id"])))
    items = []
    for raw in cast(list[str], row.details["work_ids"]):
        work_id = uuid.UUID(str(raw))
        decision = effective.get(work_id)
        if (
            filter == "UNSCREENED"
            and decision
            or filter == "HUMAN_OVERRIDDEN"
            and (not decision or decision.reviewer_type != "HUMAN")
        ):
            continue
        if filter in ("INCLUDE", "EXCLUDE", "UNCERTAIN") and (
            not decision or decision.decision != filter
        ):
            continue
        items.append(
            {"work_id": work_id, "effective": decision_view(decision) if decision else None}
        )
    return items[offset : offset + limit]


@router.post("/{project_id}/works/{work_id}/screening-decisions", status_code=201)
async def human_decision(
    project_id: uuid.UUID, work_id: uuid.UUID, data: HumanDecision, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    row = await selected_round(project_id, session, data.round_id)
    if not row or str(work_id) not in cast(list[str], row.details["work_ids"]):
        raise error(404, "NOT_FOUND", "Work is not in this screening round")
    if data.decision == "EXCLUDE" and not data.reason_code:
        raise error(422, "USER_INPUT_ERROR", "Select an exclusion reason")
    decision = ScreeningDecision(
        project_id=project_id,
        work_id=work_id,
        protocol_id=uuid.UUID(str(row.details["protocol_id"])),
        protocol_version=int(str(row.details["protocol_version"])),
        round_id=row.id,
        stage="TITLE_ABSTRACT",
        decision=data.decision,
        reason_code=data.reason_code if data.decision == "EXCLUDE" else None,
        rationale=data.note or (data.reason_code.value if data.reason_code else "Human review"),
        reviewer_type="HUMAN",
        reviewer_id=user.id,
    )
    session.add(decision)
    await session.flush()
    append_event(
        session,
        project,
        user,
        "SCREENING_HUMAN_DECISION",
        decision_id=str(decision.id),
        work_id=str(work_id),
    )
    return decision_view(decision)


@router.get("/{project_id}/works/{work_id}/screening-history")
async def history(project_id: uuid.UUID, work_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    rows = await session.scalars(
        select(ScreeningDecision)
        .where(ScreeningDecision.project_id == project_id, ScreeningDecision.work_id == work_id)
        .order_by(ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc())
    )
    return [decision_view(row) for row in rows]

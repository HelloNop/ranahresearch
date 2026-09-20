import asyncio
import hmac
import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from ranah_agents.research import FrameworkOutput, PlanOutput, SearchFilters, StrategyOutput
from ranah_domain.db import create_engine, create_session_factory, session_scope
from ranah_domain.enums import (
    ProjectEventActorType,
    ProjectMemberRole,
    ProjectStatus,
    ResearchPlanStatus,
    WorkflowRunStatus,
)
from ranah_domain.models.dedupe import DuplicateDecision, DuplicateMember
from ranah_domain.models.events import ProjectEvent
from ranah_domain.models.organization import ProjectMember, User
from ranah_domain.models.project import (
    ResearchFramework,
    ResearchIdea,
    ResearchPlan,
    ResearchProject,
)
from ranah_domain.models.search import SearchQuery, SearchRun, SearchStrategy
from ranah_domain.models.work import (
    WorkIdentifier,
    WorkMetadataObservation,
    WorkRecord,
    WorkVerification,
)
from ranah_domain.models.workflow import WorkflowRun
from ranah_workflow import connect_client
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.exceptions import WorkflowAlreadyStartedError

router = APIRouter(prefix="/projects", tags=["Research discovery"])


@lru_cache
def session_factory():  # type: ignore[no-untyped-def]
    return create_session_factory(create_engine())


async def database() -> AsyncIterator[AsyncSession]:
    async with session_scope(session_factory()) as session:
        yield session


DB = Annotated[AsyncSession, Depends(database)]


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


async def authenticated_user(
    session: DB, authorization: Annotated[str | None, Header()] = None
) -> User:
    token = authorization.removeprefix("Bearer ") if authorization else ""
    credentials = json.loads(os.environ.get("RANAH_API_TOKENS", "{}"))
    subject = next(
        (value for key, value in credentials.items() if token and hmac.compare_digest(token, key)),
        None,
    )
    user = await session.get(User, uuid.UUID(subject)) if subject else None
    if user is None or user.status != "ACTIVE":
        raise error(401, "PERMISSION_ERROR", "A valid access token is required")
    return user


Principal = Annotated[User, Depends(authenticated_user)]


async def scoped_project(
    session: AsyncSession, user: User, project_id: uuid.UUID, *, write: bool = False
) -> ResearchProject:
    project = await session.scalar(
        select(ResearchProject)
        .where(
            ResearchProject.id == project_id,
            ResearchProject.organization_id == user.organization_id,
        )
        .with_for_update()
        if write
        else select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.organization_id == user.organization_id,
        )
    )
    member = await session.get(ProjectMember, (project_id, user.id)) if project else None
    if project is None or member is None:
        raise error(404, "NOT_FOUND", "Project not found")
    if write and member.role not in (ProjectMemberRole.OWNER, ProjectMemberRole.EDITOR):
        raise error(403, "PERMISSION_ERROR", "Editing this project is not permitted")
    return project


class CreateProject(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    idea: str = Field(min_length=1, max_length=12000)


class IdeaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    idea: str = Field(min_length=1, max_length=12000)


class RecordView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class IdeaView(RecordView):
    raw_text: str
    created_at: datetime


class OperationView(BaseModel):
    operation_id: uuid.UUID
    status: WorkflowRunStatus
    stage: str
    error: str | None
    provider_runs: list[dict[str, Any]] = Field(default_factory=list)


class ProjectView(RecordView):
    title: str
    status: ProjectStatus
    ideas: list[IdeaView]
    literature_count: int
    plan_status: ResearchPlanStatus | None
    operation: OperationView | None


class PlanView(RecordView):
    version: int
    status: ResearchPlanStatus
    content: PlanOutput
    created_by_agent_run_id: uuid.UUID | None


class FrameworkView(RecordView):
    version: int
    structured_elements: FrameworkOutput


class StrategyView(RecordView):
    version: int
    content: StrategyOutput


class Approval(BaseModel):
    plan_id: uuid.UUID


class LiteratureView(RecordView):
    title: str
    abstract: str | None
    authors: list[str]
    publication_year: int | None
    doi: str | None
    venue: str | None
    discovered_via: list[str]
    verification_status: str
    verification: dict[str, Any] | None
    duplicate_status: str
    identifiers: list[dict[str, str]]
    provenance: list[dict[str, Any]]


class EventView(RecordView):
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


def append_event(
    session: AsyncSession, project: ResearchProject, user: User, name: str, **payload: Any
) -> None:
    session.add(
        ProjectEvent(
            project_id=project.id,
            event_type=name,
            actor_type=ProjectEventActorType.USER,
            actor_id=user.id,
            payload=payload,
        )
    )


async def latest_plan(session: AsyncSession, project_id: uuid.UUID) -> ResearchPlan | None:
    return (
        await session.scalars(
            select(ResearchPlan)
            .where(ResearchPlan.project_id == project_id)
            .order_by(ResearchPlan.version.desc())
            .limit(1)
        )
    ).first()


async def operation_view(session: AsyncSession, row: WorkflowRun) -> OperationView:
    runs = await session.scalars(select(SearchRun).where(SearchRun.operation_id == row.id))
    return OperationView(
        operation_id=row.id,
        status=row.status,
        stage=row.stage,
        error=str(row.details["error"]) if row.details.get("error") else None,
        provider_runs=[
            {
                "provider": run.provider,
                "status": run.status.value,
                "retrieved": run.result_count_retrieved,
                **run.provider_metadata,
            }
            for run in runs
        ],
    )


async def project_view(session: AsyncSession, project: ResearchProject) -> ProjectView:
    ideas = await session.scalars(
        select(ResearchIdea)
        .where(ResearchIdea.project_id == project.id)
        .order_by(ResearchIdea.created_at)
    )
    plan = await latest_plan(session, project.id)
    op = await session.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project.id)
        .order_by(WorkflowRun.started_at.desc())
        .limit(1)
    )
    return ProjectView(
        id=project.id,
        title=project.title,
        status=project.status,
        ideas=[IdeaView.model_validate(idea) for idea in ideas],
        literature_count=await session.scalar(
            select(func.count()).select_from(WorkRecord).where(WorkRecord.project_id == project.id)
        )
        or 0,
        plan_status=plan.status if plan else None,
        operation=await operation_view(session, op) if op else None,
    )


@router.post("", response_model=ProjectView, status_code=201)
async def create_project(data: CreateProject, session: DB, user: Principal) -> ProjectView:
    project = ResearchProject(
        organization_id=user.organization_id,
        created_by=user.id,
        title=data.title or data.idea[:120],
        status=ProjectStatus.IDEA,
    )
    session.add(project)
    await session.flush()
    session.add_all(
        [
            ResearchIdea(project_id=project.id, raw_text=data.idea, created_by=user.id),
            ProjectMember(project_id=project.id, user_id=user.id, role=ProjectMemberRole.OWNER),
        ]
    )
    append_event(session, project, user, "PROJECT_CREATED")
    await session.flush()
    return await project_view(session, project)


@router.get("", response_model=list[ProjectView])
async def list_projects(session: DB, user: Principal) -> list[ProjectView]:
    projects = await session.scalars(
        select(ResearchProject)
        .join(ProjectMember)
        .where(
            ResearchProject.organization_id == user.organization_id,
            ProjectMember.user_id == user.id,
        )
        .order_by(ResearchProject.created_at.desc())
        .limit(100)
    )
    return [await project_view(session, project) for project in projects]


@router.get("/{project_id}", response_model=ProjectView)
async def get_project(project_id: uuid.UUID, session: DB, user: Principal) -> ProjectView:
    return await project_view(session, await scoped_project(session, user, project_id))


async def ensure_idle(session: AsyncSession, project_id: uuid.UUID) -> None:
    if await session.scalar(
        select(WorkflowRun.id)
        .where(
            WorkflowRun.project_id == project_id,
            WorkflowRun.status.in_([WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING]),
        )
        .limit(1)
    ):
        raise error(409, "WORKFLOW_CONFLICT", "Wait for the current operation to finish")


@router.post("/{project_id}/ideas", response_model=IdeaView, status_code=201)
async def add_idea(
    project_id: uuid.UUID, data: IdeaRequest, session: DB, user: Principal
) -> IdeaView:
    project = await scoped_project(session, user, project_id, write=True)
    await ensure_idle(session, project_id)
    idea = ResearchIdea(project_id=project_id, raw_text=data.idea, created_by=user.id)
    session.add(idea)
    plan = await latest_plan(session, project_id)
    if plan:
        plan.status = ResearchPlanStatus.SUPERSEDED
    project.status = ProjectStatus.IDEA
    append_event(session, project, user, "IDEA_ADDED")
    await session.flush()
    return IdeaView.model_validate(idea)


@router.get("/{project_id}/plan", response_model=PlanView | None)
async def get_plan(project_id: uuid.UUID, session: DB, user: Principal) -> PlanView | None:
    await scoped_project(session, user, project_id)
    plan = await latest_plan(session, project_id)
    return PlanView.model_validate(plan) if plan else None


async def dispatch(row: WorkflowRun) -> None:
    client = await connect_client()
    args: list[Any] = [str(row.id), str(row.details["kind"])]
    if row.workflow_type == "ResearchDiscoveryWorkflow":
        args = [
            str(row.id),
            str(row.project_id),
            row.details["strategy_id"],
            row.details["query_ids"],
        ]
    try:
        await client.start_workflow(
            row.workflow_type,
            args=args,
            id=row.temporal_workflow_id,
            task_queue=os.environ.get("RANAH_TASK_QUEUE", "orchestration"),
        )
    except WorkflowAlreadyStartedError:
        pass


async def start_operation(
    session: AsyncSession, project: ResearchProject, kind: str, details: dict[str, Any]
) -> OperationView:
    await ensure_idle(session, project.id)
    op_id = uuid.uuid4()
    row = WorkflowRun(
        id=op_id,
        project_id=project.id,
        temporal_workflow_id=f"research-{op_id}",
        status=WorkflowRunStatus.PENDING,
        workflow_type="ResearchDiscoveryWorkflow"
        if kind == "search"
        else "ResearchPlanningWorkflow",
        stage="PENDING",
        details={"kind": kind, **details},
    )
    session.add(row)
    await session.commit()
    try:
        await asyncio.wait_for(dispatch(row), timeout=5)
    except Exception:
        # Persisted PENDING commands are resubmitted by the operation polling endpoint.
        return await operation_view(session, row)
    return await operation_view(session, row)


@router.post("/{project_id}/plan/generate", response_model=OperationView, status_code=202)
async def generate_plan(project_id: uuid.UUID, session: DB, user: Principal) -> OperationView:
    project = await scoped_project(session, user, project_id, write=True)
    idea = await session.scalar(
        select(ResearchIdea)
        .where(ResearchIdea.project_id == project_id)
        .order_by(ResearchIdea.created_at.desc())
        .limit(1)
    )
    if not idea:
        raise error(409, "USER_INPUT_ERROR", "Add a research idea first")
    return await start_operation(session, project, "plan", {"idea_id": str(idea.id)})


@router.post("/{project_id}/plan/approve", response_model=PlanView)
async def approve_plan(
    project_id: uuid.UUID, data: Approval, session: DB, user: Principal
) -> PlanView:
    project = await scoped_project(session, user, project_id, write=True)
    await ensure_idle(session, project_id)
    plan = await latest_plan(session, project_id)
    framework = await session.scalar(
        select(ResearchFramework).where(ResearchFramework.research_plan_id == data.plan_id)
    )
    if (
        not plan
        or plan.id != data.plan_id
        or not framework
        or plan.status not in (ResearchPlanStatus.PROPOSED, ResearchPlanStatus.APPROVED)
    ):
        raise error(409, "WORKFLOW_CONFLICT", "Approve the current proposed plan with a framework")
    if plan.status != ResearchPlanStatus.APPROVED:
        plan.status = ResearchPlanStatus.APPROVED
        plan.approved_by, plan.approved_at = user.id, datetime.now(UTC)
        project.working_title = plan.provisional_title
        project.research_method = plan.recommended_method
        append_event(session, project, user, "RESEARCH_PLAN_APPROVED", plan_id=str(plan.id))
    return PlanView.model_validate(plan)


@router.get("/{project_id}/framework", response_model=FrameworkView | None)
async def get_framework(
    project_id: uuid.UUID, session: DB, user: Principal
) -> FrameworkView | None:
    await scoped_project(session, user, project_id)
    plan = await latest_plan(session, project_id)
    row = (
        await session.scalar(
            select(ResearchFramework).where(ResearchFramework.research_plan_id == plan.id)
        )
        if plan
        else None
    )
    return FrameworkView.model_validate(row) if row else None


@router.post(
    "/{project_id}/search-strategy/generate", response_model=OperationView, status_code=202
)
async def generate_strategy(
    project_id: uuid.UUID, data: SearchFilters, session: DB, user: Principal
) -> OperationView:
    project = await scoped_project(session, user, project_id, write=True)
    plan = await latest_plan(session, project_id)
    if not plan or plan.status != ResearchPlanStatus.APPROVED:
        raise error(409, "WORKFLOW_CONFLICT", "Approve the current research plan first")
    return await start_operation(
        session,
        project,
        "strategy",
        {
            "plan_id": str(plan.id),
            "filters": data.model_dump(),
        },
    )


async def latest_strategy(session: AsyncSession, project_id: uuid.UUID) -> SearchStrategy | None:
    plan = await latest_plan(session, project_id)
    if not plan or plan.status != ResearchPlanStatus.APPROVED:
        return None
    return (
        await session.scalars(
            select(SearchStrategy)
            .where(
                SearchStrategy.project_id == project_id, SearchStrategy.research_plan_id == plan.id
            )
            .order_by(SearchStrategy.version.desc())
            .limit(1)
        )
    ).first()


@router.get("/{project_id}/search-strategy", response_model=StrategyView | None)
async def get_strategy(project_id: uuid.UUID, session: DB, user: Principal) -> StrategyView | None:
    await scoped_project(session, user, project_id)
    row = await latest_strategy(session, project_id)
    return StrategyView.model_validate(row) if row else None


@router.post("/{project_id}/literature/search", response_model=OperationView, status_code=202)
async def start_search(project_id: uuid.UUID, session: DB, user: Principal) -> OperationView:
    project = await scoped_project(session, user, project_id, write=True)
    strategy = await latest_strategy(session, project_id)
    if not strategy:
        raise error(409, "WORKFLOW_CONFLICT", "Generate a strategy for the approved plan first")
    query_ids = list(
        await session.scalars(
            select(SearchQuery.id).where(SearchQuery.search_strategy_id == strategy.id)
        )
    )
    project.status = ProjectStatus.SEARCHING
    return await start_operation(
        session,
        project,
        "search",
        {
            "strategy_id": str(strategy.id),
            "query_ids": list(map(str, query_ids)),
        },
    )


@router.get("/{project_id}/operations/{operation_id}", response_model=OperationView)
async def get_operation(
    project_id: uuid.UUID, operation_id: uuid.UUID, session: DB, user: Principal
) -> OperationView:
    await scoped_project(session, user, project_id)
    row = await session.scalar(
        select(WorkflowRun).where(
            WorkflowRun.id == operation_id, WorkflowRun.project_id == project_id
        )
    )
    if row is None:
        raise error(404, "NOT_FOUND", "Operation not found")
    if row.status == WorkflowRunStatus.PENDING:
        try:
            await asyncio.wait_for(dispatch(row), timeout=5)
        except Exception:
            view = await operation_view(session, row)
            view.error = "Temporal is unavailable; this queued operation will retry on refresh"
            return view
    return await operation_view(session, row)


@router.get("/{project_id}/events", response_model=list[EventView])
async def get_events(project_id: uuid.UUID, session: DB, user: Principal) -> list[EventView]:
    await scoped_project(session, user, project_id)
    rows = await session.scalars(
        select(ProjectEvent)
        .where(ProjectEvent.project_id == project_id)
        .order_by(ProjectEvent.created_at.desc())
        .limit(200)
    )
    return [EventView.model_validate(row) for row in rows]


@router.get("/{project_id}/literature", response_model=list[LiteratureView])
async def get_literature(
    project_id: uuid.UUID,
    session: DB,
    user: Principal,
    year: int | None = None,
    verification_status: str | None = None,
    provider: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LiteratureView]:
    await scoped_project(session, user, project_id)
    stmt = select(WorkRecord).where(WorkRecord.project_id == project_id)
    if year is not None:
        stmt = stmt.where(WorkRecord.publication_year == year)
    if provider:
        stmt = stmt.where(
            select(WorkMetadataObservation.id)
            .where(
                WorkMetadataObservation.work_id == WorkRecord.id,
                WorkMetadataObservation.provider == provider,
            )
            .exists()
        )
    if verification_status:
        latest = select(WorkVerification.status).where(WorkVerification.work_id == WorkRecord.id)
        stmt = stmt.where(
            func.coalesce(
                latest.order_by(WorkVerification.verified_at.desc()).limit(1).scalar_subquery(),
                "UNVERIFIED",
            )
            == verification_status
        )
    works = await session.scalars(
        stmt.order_by(WorkRecord.created_at.desc()).limit(limit).offset(offset)
    )
    result = []
    for work in works:
        observations = list(
            await session.scalars(
                select(WorkMetadataObservation)
                .where(WorkMetadataObservation.work_id == work.id)
                .order_by(WorkMetadataObservation.observed_at)
            )
        )
        identifiers = await session.scalars(
            select(WorkIdentifier).where(WorkIdentifier.work_id == work.id)
        )
        verification = await session.scalar(
            select(WorkVerification)
            .where(WorkVerification.work_id == work.id)
            .order_by(WorkVerification.verified_at.desc())
            .limit(1)
        )
        duplicate = await session.scalar(
            select(DuplicateDecision)
            .join(
                DuplicateMember,
                DuplicateMember.duplicate_group_id == DuplicateDecision.duplicate_group_id,
            )
            .where(DuplicateMember.work_id == work.id)
            .order_by(DuplicateDecision.created_at.desc())
            .limit(1)
        )
        authors = next(
            (
                o.field_value.get("value", [])
                for o in reversed(observations)
                if o.field_name == "authors"
            ),
            [],
        )
        result.append(
            LiteratureView(
                id=work.id,
                title=work.title,
                abstract=work.abstract,
                authors=cast(list[str], authors),
                publication_year=work.publication_year,
                doi=work.doi,
                venue=work.journal,
                discovered_via=sorted({o.provider for o in observations}),
                verification_status=verification.status.value if verification else "UNVERIFIED",
                verification=verification.details if verification else None,
                duplicate_status=duplicate.decision.value if duplicate else "NO_DUPLICATE_DETECTED",
                identifiers=[
                    {"provider": i.provider, "identifier": i.identifier} for i in identifiers
                ],
                provenance=[
                    {"provider": o.provider, "field": o.field_name, "value": o.field_value}
                    for o in observations
                ],
            )
        )
    return result

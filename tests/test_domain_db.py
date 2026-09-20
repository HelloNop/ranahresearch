"""EPIC-003 acceptance tests: persistence, tenant scoping, and key constraints."""

import uuid

import pytest
from ranah_domain.enums import (
    AgentRunStatus,
    ProjectEventActorType,
    SearchRunStatus,
    WorkVerificationStatus,
    WorkVerificationType,
)
from ranah_domain.models.organization import Organization
from ranah_domain.repositories import agents as agents_repo
from ranah_domain.repositories import events as events_repo
from ranah_domain.repositories import projects as projects_repo
from ranah_domain.repositories import search as search_repo
from ranah_domain.repositories import work as work_repo
from ranah_domain.repositories import workflow as workflow_repo
from ranah_domain.schemas.agent import AgentDefinitionCreate, AgentRunComplete, AgentRunCreate
from ranah_domain.schemas.events import ProjectEventCreate
from ranah_domain.schemas.project import (
    ResearchIdeaCreate,
    ResearchPlanCreate,
    ResearchProjectCreate,
)
from ranah_domain.schemas.search import (
    SearchQueryCreate,
    SearchResultCreate,
    SearchRunCreate,
    SearchStrategyCreate,
)
from ranah_domain.schemas.work import (
    WorkMetadataObservationCreate,
    WorkRecordCreate,
    WorkVerificationCreate,
)
from ranah_domain.schemas.workflow import WorkflowRunCreate
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_organization(session: AsyncSession) -> Organization:
    org = Organization(name="Test Org", slug=f"org-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    return org


async def _make_project(session: AsyncSession) -> uuid.UUID:
    org = await _make_organization(session)
    project = await projects_repo.create_project(
        session, ResearchProjectCreate(organization_id=org.id, title="Test project")
    )
    return project.id


async def test_project_create_and_read(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    fetched = await projects_repo.get_project(db_session, project_id)
    assert fetched is not None
    assert fetched.title == "Test project"


async def test_idea_attaches_to_project(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    idea = await projects_repo.create_idea(
        db_session, ResearchIdeaCreate(project_id=project_id, raw_text="Does X affect Y?")
    )
    ideas = await projects_repo.list_ideas(db_session, project_id)
    assert [i.id for i in ideas] == [idea.id]


async def test_plan_versions_are_stored(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    await projects_repo.create_plan(
        db_session, ResearchPlanCreate(project_id=project_id, version=1, objective="v1")
    )
    await projects_repo.create_plan(
        db_session, ResearchPlanCreate(project_id=project_id, version=2, objective="v2")
    )
    versions = await projects_repo.list_plan_versions(db_session, project_id)
    assert [p.version for p in versions] == [1, 2]


async def test_search_strategy_query_and_run_persist(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    strategy = await search_repo.create_strategy(
        db_session, SearchStrategyCreate(project_id=project_id)
    )
    query = await search_repo.create_query(
        db_session,
        SearchQueryCreate(
            search_strategy_id=strategy.id, provider="openalex", query_text="cats AND dogs"
        ),
    )
    run = await search_repo.create_run(
        db_session,
        SearchRunCreate(
            project_id=project_id,
            search_query_id=query.id,
            provider="openalex",
            executed_query="cats AND dogs",
        ),
    )
    assert run.status == SearchRunStatus.RUNNING
    completed = await search_repo.complete_run(
        db_session,
        run.id,
        status=SearchRunStatus.COMPLETED,
        result_count_reported=10,
        result_count_retrieved=10,
    )
    assert completed.status == SearchRunStatus.COMPLETED
    result = await search_repo.add_result(
        db_session, SearchResultCreate(search_run_id=run.id, provider_record_id="W123")
    )
    assert result.search_run_id == run.id


async def test_work_record_and_metadata_observation_persist(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    work = await work_repo.create_work_record(
        db_session,
        WorkRecordCreate(project_id=project_id, title="A study of things", doi="10.1/abc"),
    )
    observation = await work_repo.add_metadata_observation(
        db_session,
        WorkMetadataObservationCreate(
            work_id=work.id,
            provider="openalex",
            field_name="title",
            field_value={"value": "A study"},
        ),
    )
    assert observation.work_id == work.id

    verification = await work_repo.add_verification(
        db_session,
        WorkVerificationCreate(
            work_id=work.id,
            verification_type=WorkVerificationType.DOI_IDENTITY,
            status=WorkVerificationStatus.VERIFIED,
        ),
    )
    assert verification.status == WorkVerificationStatus.VERIFIED

    fetched = await work_repo.get_by_doi(db_session, project_id, "10.1/abc")
    assert fetched is not None and fetched.id == work.id


async def test_project_events_are_appendable(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    await events_repo.append_event(
        db_session,
        ProjectEventCreate(
            project_id=project_id,
            event_type="PROJECT_CREATED",
            actor_type=ProjectEventActorType.SYSTEM,
        ),
    )
    events = await events_repo.list_events(db_session, project_id)
    assert [e.event_type for e in events] == ["PROJECT_CREATED"]


async def test_agent_run_lifecycle_persists(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    definition = await agents_repo.create_agent_definition(
        db_session, AgentDefinitionCreate(name="sample_agent", version="v1")
    )
    run = await agents_repo.start_agent_run(
        db_session,
        AgentRunCreate(
            project_id=project_id, agent_definition_id=definition.id, task_type="SAMPLE"
        ),
    )
    assert run.status == AgentRunStatus.RUNNING
    completed = await agents_repo.complete_agent_run(
        db_session, run.id, AgentRunComplete(status=AgentRunStatus.SUCCESS)
    )
    assert completed.status == AgentRunStatus.SUCCESS
    assert completed.completed_at is not None


async def test_workflow_run_persists(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    run = await workflow_repo.create_workflow_run(
        db_session,
        WorkflowRunCreate(
            project_id=project_id,
            temporal_workflow_id=f"wf-{uuid.uuid4()}",
            workflow_type="ResearchFoundationWorkflow",
        ),
    )
    fetched = await workflow_repo.get_by_temporal_id(db_session, run.temporal_workflow_id)
    assert fetched is not None and fetched.id == run.id


async def test_project_member_unique_constraint(db_session: AsyncSession) -> None:
    from ranah_domain.enums import ProjectMemberRole
    from ranah_domain.repositories import organizations as orgs_repo
    from ranah_domain.schemas.organization import ProjectMemberCreate, UserCreate

    org = await _make_organization(db_session)
    project = await projects_repo.create_project(
        db_session, ResearchProjectCreate(organization_id=org.id, title="Membership project")
    )
    user = await orgs_repo.create_user(
        db_session,
        UserCreate(
            organization_id=org.id,
            email=f"{uuid.uuid4().hex}@example.com",
            display_name="Reviewer",
            auth_provider="google",
            provider_subject=uuid.uuid4().hex,
        ),
    )
    await orgs_repo.add_project_member(
        db_session,
        ProjectMemberCreate(project_id=project.id, user_id=user.id, role=ProjectMemberRole.OWNER),
    )
    with pytest.raises(IntegrityError):
        await orgs_repo.add_project_member(
            db_session,
            ProjectMemberCreate(
                project_id=project.id, user_id=user.id, role=ProjectMemberRole.VIEWER
            ),
        )


async def test_work_record_requires_project_fk(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await work_repo.create_work_record(
            db_session, WorkRecordCreate(project_id=uuid.uuid4(), title="Orphan work")
        )

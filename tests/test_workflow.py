"""EPIC-005 acceptance tests: run against the local Temporal server from `make infra-up`."""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from _flaky_workflow import FlakyWorkflow, attempts, flaky_activity
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.enums import WorkflowRunStatus
from ranah_domain.repositories import organizations as organizations_repo
from ranah_domain.repositories import projects as projects_repo
from ranah_domain.repositories import workflow as workflow_repo
from ranah_domain.schemas.organization import OrganizationCreate
from ranah_domain.schemas.project import ResearchProjectCreate
from ranah_worker_orchestration import activities
from ranah_worker_orchestration.workflows import ResearchFoundationWorkflow
from ranah_workflow import TemporalSettings, connect_client
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from temporalio import activity
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowFailureError
from temporalio.exceptions import CancelledError
from temporalio.worker import Worker


@pytest_asyncio.fixture
async def temporal_client() -> AsyncIterator[Client]:
    yield await connect_client(TemporalSettings())


@pytest_asyncio.fixture
async def committed_project_id(db_engine: AsyncEngine) -> str:
    """A ResearchProject committed for real, visible to the activity's own DB session."""
    session_factory = create_session_factory(db_engine)
    async with session_scope(session_factory) as session:
        org = await organizations_repo.create_organization(
            session, OrganizationCreate(name="Workflow test org", slug=f"wf-{uuid.uuid4().hex[:8]}")
        )
        project = await projects_repo.create_project(
            session, ResearchProjectCreate(organization_id=org.id, title="Workflow test project")
        )
        return str(project.id)


async def test_research_foundation_workflow_completes_and_persists(
    temporal_client: Client, db_session: AsyncSession, committed_project_id: str
) -> None:
    task_queue = f"orchestration-test-{uuid.uuid4().hex[:8]}"
    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[ResearchFoundationWorkflow],
        activities=[
            activities.create_workflow_run,
            activities.update_workflow_run_status,
            activities.prepare_scope,
            activities.finalize_scope,
        ],
    ):
        handle = await temporal_client.start_workflow(
            ResearchFoundationWorkflow.run,
            committed_project_id,
            id=f"research-foundation-{uuid.uuid4().hex[:12]}",
            task_queue=task_queue,
        )
        await handle.signal(ResearchFoundationWorkflow.add_note, "reviewed by test")
        result = await handle.result()

    assert result["result"]["finalized"] is True
    assert result["notes"] == ["reviewed by test"]

    run = await workflow_repo.get_by_temporal_id(db_session, handle.id)
    assert run is not None
    assert run.status == WorkflowRunStatus.COMPLETED


async def test_research_foundation_workflow_cancellation(
    temporal_client: Client, db_session: AsyncSession, committed_project_id: str
) -> None:
    task_queue = f"orchestration-test-{uuid.uuid4().hex[:8]}"

    @activity.defn(name="prepare_scope")
    async def slow_prepare_scope(project_id: str) -> dict[str, str]:
        for _ in range(300):
            activity.heartbeat()
            await asyncio.sleep(0.1)
        return {"project_id": project_id}

    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[ResearchFoundationWorkflow],
        activities=[
            activities.create_workflow_run,
            activities.update_workflow_run_status,
            slow_prepare_scope,
            activities.finalize_scope,
        ],
    ):
        handle = await temporal_client.start_workflow(
            ResearchFoundationWorkflow.run,
            committed_project_id,
            id=f"research-foundation-{uuid.uuid4().hex[:12]}",
            task_queue=task_queue,
        )
        # Wait until the WorkflowRun row exists (create_workflow_run has run), so we
        # cancel while inside the heartbeating prepare_scope activity, not before it.
        for _ in range(100):
            if await workflow_repo.get_by_temporal_id(db_session, handle.id) is not None:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("WorkflowRun row was never created")

        await handle.cancel()
        with pytest.raises(WorkflowFailureError) as exc_info:
            await handle.result()
        assert isinstance(exc_info.value.cause, CancelledError)

    description = await handle.describe()
    assert description.status == WorkflowExecutionStatus.CANCELED

    # The WorkflowRun row from create_workflow_run exists; a cancelled run does not
    # get a further status update from inside the workflow itself (see workflows.py).
    run = await workflow_repo.get_by_temporal_id(db_session, handle.id)
    assert run is not None


async def test_activity_retries_on_transient_failure(temporal_client: Client) -> None:
    task_queue = f"orchestration-test-{uuid.uuid4().hex[:8]}"
    key = uuid.uuid4().hex
    async with Worker(
        temporal_client,
        task_queue=task_queue,
        workflows=[FlakyWorkflow],
        activities=[flaky_activity],
    ):
        result = await temporal_client.execute_workflow(
            FlakyWorkflow.run,
            key,
            id=f"flaky-{key}",
            task_queue=task_queue,
        )
    assert result == "ok"
    assert attempts[key] == 3

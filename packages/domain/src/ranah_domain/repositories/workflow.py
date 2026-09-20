import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.enums import WorkflowRunStatus
from ranah_domain.models.workflow import WorkflowRun
from ranah_domain.schemas.workflow import WorkflowRunCreate


async def create_workflow_run(session: AsyncSession, data: WorkflowRunCreate) -> WorkflowRun:
    run = WorkflowRun(status=WorkflowRunStatus.RUNNING, **data.model_dump())
    session.add(run)
    await session.flush()
    return run


async def get_by_temporal_id(
    session: AsyncSession, temporal_workflow_id: str
) -> WorkflowRun | None:
    stmt = select(WorkflowRun).where(WorkflowRun.temporal_workflow_id == temporal_workflow_id)
    return (await session.scalars(stmt)).first()


async def update_workflow_run_status(
    session: AsyncSession, run_id: uuid.UUID, status: WorkflowRunStatus
) -> WorkflowRun:
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise ValueError(f"WorkflowRun {run_id} not found")
    run.status = status
    if status in (
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    ):
        run.completed_at = datetime.now(UTC)
    await session.flush()
    return run

"""Activities for ResearchFoundationWorkflow.

Everything non-deterministic (DB writes, clocks) lives here, never in the
workflow body. Each activity opens its own short-lived DB session: agents and
activities are stateless workers, not long-lived stateful processes.
"""

import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from ranah_domain.db import create_engine, create_session_factory, session_scope
from ranah_domain.enums import WorkflowRunStatus
from ranah_domain.repositories import workflow as workflow_repo
from ranah_domain.schemas.workflow import WorkflowRunCreate
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity


@lru_cache
def _session_factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(create_engine())


@activity.defn
async def create_workflow_run(
    project_id: str, temporal_workflow_id: str, workflow_type: str
) -> str:
    async with session_scope(_session_factory()) as session:
        run = await workflow_repo.create_workflow_run(
            session,
            WorkflowRunCreate(
                project_id=uuid.UUID(project_id),
                temporal_workflow_id=temporal_workflow_id,
                workflow_type=workflow_type,
            ),
        )
        return str(run.id)


@activity.defn
async def update_workflow_run_status(run_id: str, status: str) -> None:
    async with session_scope(_session_factory()) as session:
        await workflow_repo.update_workflow_run_status(
            session, uuid.UUID(run_id), WorkflowRunStatus(status)
        )


@activity.defn
async def prepare_scope(project_id: str) -> dict[str, Any]:
    """Stand-in for real work (an LLM call, a provider search, ...)."""
    activity.logger.info("preparing scope for project %s", project_id)
    return {"project_id": project_id, "prepared_at": datetime.now(UTC).isoformat()}


@activity.defn
async def finalize_scope(prepared: dict[str, Any]) -> dict[str, Any]:
    activity.logger.info("finalizing scope for project %s", prepared.get("project_id"))
    return {**prepared, "finalized": True}

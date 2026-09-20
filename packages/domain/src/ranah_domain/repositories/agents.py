import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.enums import AgentRunStatus
from ranah_domain.models.agent import AgentDefinition, AgentRun
from ranah_domain.schemas.agent import AgentDefinitionCreate, AgentRunComplete, AgentRunCreate


async def create_agent_definition(
    session: AsyncSession, data: AgentDefinitionCreate
) -> AgentDefinition:
    definition = AgentDefinition(**data.model_dump())
    session.add(definition)
    await session.flush()
    return definition


async def get_by_name_version(
    session: AsyncSession, name: str, version: str
) -> AgentDefinition | None:
    stmt = select(AgentDefinition).where(
        AgentDefinition.name == name, AgentDefinition.version == version
    )
    return (await session.scalars(stmt)).first()


async def get_or_create_definition(
    session: AsyncSession, data: AgentDefinitionCreate
) -> AgentDefinition:
    existing = await get_by_name_version(session, data.name, data.version)
    if existing is not None:
        return existing
    return await create_agent_definition(session, data)


async def start_agent_run(session: AsyncSession, data: AgentRunCreate) -> AgentRun:
    run = AgentRun(status=AgentRunStatus.RUNNING, **data.model_dump())
    session.add(run)
    await session.flush()
    return run


async def complete_agent_run(
    session: AsyncSession, run_id: uuid.UUID, data: AgentRunComplete
) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise ValueError(f"AgentRun {run_id} not found")
    run.status = data.status
    run.output_metadata = data.output_metadata
    run.input_tokens = data.input_tokens
    run.output_tokens = data.output_tokens
    run.estimated_cost = data.estimated_cost
    run.error_code = data.error_code
    run.completed_at = datetime.now(UTC)
    await session.flush()
    return run

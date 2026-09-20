import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.models.events import ProjectEvent, UsageEvent
from ranah_domain.schemas.events import ProjectEventCreate, UsageEventCreate


async def append_event(session: AsyncSession, data: ProjectEventCreate) -> ProjectEvent:
    event = ProjectEvent(**data.model_dump())
    session.add(event)
    await session.flush()
    return event


async def list_events(session: AsyncSession, project_id: uuid.UUID) -> list[ProjectEvent]:
    stmt = (
        select(ProjectEvent)
        .where(ProjectEvent.project_id == project_id)
        .order_by(ProjectEvent.created_at)
    )
    return list((await session.scalars(stmt)).all())


async def append_usage_event(session: AsyncSession, data: UsageEventCreate) -> UsageEvent:
    event = UsageEvent(**data.model_dump())
    session.add(event)
    await session.flush()
    return event

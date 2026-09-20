from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.models.dedupe import DuplicateDecision, DuplicateGroup, DuplicateMember
from ranah_domain.schemas.dedupe import (
    DuplicateDecisionCreate,
    DuplicateGroupCreate,
    DuplicateMemberCreate,
)


async def create_group(session: AsyncSession, data: DuplicateGroupCreate) -> DuplicateGroup:
    group = DuplicateGroup(**data.model_dump())
    session.add(group)
    await session.flush()
    return group


async def add_member(session: AsyncSession, data: DuplicateMemberCreate) -> DuplicateMember:
    member = DuplicateMember(**data.model_dump())
    session.add(member)
    await session.flush()
    return member


async def record_decision(
    session: AsyncSession, data: DuplicateDecisionCreate
) -> DuplicateDecision:
    decision = DuplicateDecision(**data.model_dump())
    session.add(decision)
    await session.flush()
    return decision

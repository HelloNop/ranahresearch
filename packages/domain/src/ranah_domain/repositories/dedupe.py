import uuid

from sqlalchemy import select
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


async def find_group_containing_pair(
    session: AsyncSession, work_id_a: uuid.UUID, work_id_b: uuid.UUID
) -> DuplicateGroup | None:
    """Idempotency guard: is there already a group containing both of these works?
    Re-running dedupe on the same pair should not spawn a second DuplicateGroup."""
    groups_with_a = select(DuplicateMember.duplicate_group_id).where(
        DuplicateMember.work_id == work_id_a
    )
    stmt = (
        select(DuplicateGroup)
        .join(DuplicateMember, DuplicateMember.duplicate_group_id == DuplicateGroup.id)
        .where(
            DuplicateMember.work_id == work_id_b,
            DuplicateGroup.id.in_(groups_with_a),
        )
    )
    return (await session.scalars(stmt)).first()


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

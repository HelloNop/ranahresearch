import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.models.organization import Organization, ProjectMember, User
from ranah_domain.schemas.organization import OrganizationCreate, ProjectMemberCreate, UserCreate


async def create_organization(session: AsyncSession, data: OrganizationCreate) -> Organization:
    org = Organization(name=data.name, slug=data.slug, plan=data.plan)
    session.add(org)
    await session.flush()
    return org


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        organization_id=data.organization_id,
        email=data.email,
        display_name=data.display_name,
        auth_provider=data.auth_provider,
        provider_subject=data.provider_subject,
    )
    session.add(user)
    await session.flush()
    return user


async def add_project_member(session: AsyncSession, data: ProjectMemberCreate) -> ProjectMember:
    member = ProjectMember(project_id=data.project_id, user_id=data.user_id, role=data.role)
    session.add(member)
    await session.flush()
    return member


async def get_organization(
    session: AsyncSession, organization_id: uuid.UUID
) -> Organization | None:
    return await session.get(Organization, organization_id)

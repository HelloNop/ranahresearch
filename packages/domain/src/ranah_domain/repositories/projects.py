import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.models.project import (
    ResearchFramework,
    ResearchIdea,
    ResearchPlan,
    ResearchProject,
    ResearchQuestion,
)
from ranah_domain.schemas.project import (
    ResearchFrameworkCreate,
    ResearchIdeaCreate,
    ResearchPlanCreate,
    ResearchProjectCreate,
    ResearchQuestionCreate,
)


async def create_project(session: AsyncSession, data: ResearchProjectCreate) -> ResearchProject:
    project = ResearchProject(**data.model_dump())
    session.add(project)
    await session.flush()
    return project


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> ResearchProject | None:
    return await session.get(ResearchProject, project_id)


async def list_projects(session: AsyncSession, organization_id: uuid.UUID) -> list[ResearchProject]:
    stmt = select(ResearchProject).where(ResearchProject.organization_id == organization_id)
    return list((await session.scalars(stmt)).all())


async def create_idea(session: AsyncSession, data: ResearchIdeaCreate) -> ResearchIdea:
    idea = ResearchIdea(**data.model_dump())
    session.add(idea)
    await session.flush()
    return idea


async def list_ideas(session: AsyncSession, project_id: uuid.UUID) -> list[ResearchIdea]:
    stmt = select(ResearchIdea).where(ResearchIdea.project_id == project_id)
    return list((await session.scalars(stmt)).all())


async def create_plan(session: AsyncSession, data: ResearchPlanCreate) -> ResearchPlan:
    plan = ResearchPlan(**data.model_dump())
    session.add(plan)
    await session.flush()
    return plan


async def list_plan_versions(session: AsyncSession, project_id: uuid.UUID) -> list[ResearchPlan]:
    stmt = (
        select(ResearchPlan)
        .where(ResearchPlan.project_id == project_id)
        .order_by(ResearchPlan.version)
    )
    return list((await session.scalars(stmt)).all())


async def create_question(session: AsyncSession, data: ResearchQuestionCreate) -> ResearchQuestion:
    question = ResearchQuestion(**data.model_dump())
    session.add(question)
    await session.flush()
    return question


async def create_framework(
    session: AsyncSession, data: ResearchFrameworkCreate
) -> ResearchFramework:
    framework = ResearchFramework(**data.model_dump())
    session.add(framework)
    await session.flush()
    return framework

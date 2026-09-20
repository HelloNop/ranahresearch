import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import (
    AutonomyMode,
    ProjectStatus,
    ResearchFrameworkType,
    ResearchMethod,
    ResearchPlanStatus,
)
from ranah_domain.schemas.common import OrmModel


class ResearchProjectCreate(BaseModel):
    organization_id: uuid.UUID
    created_by: uuid.UUID | None = None
    title: str
    working_title: str | None = None
    description: str | None = None
    research_method: ResearchMethod | None = None
    language: str = "en"
    autonomy_mode: AutonomyMode = AutonomyMode.BALANCED


class ResearchProjectRead(OrmModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID | None
    title: str
    working_title: str | None
    description: str | None
    research_method: ResearchMethod | None
    status: ProjectStatus
    language: str
    autonomy_mode: AutonomyMode
    created_at: datetime
    updated_at: datetime


class ResearchIdeaCreate(BaseModel):
    project_id: uuid.UUID
    raw_text: str
    created_by: uuid.UUID | None = None
    source: str = "USER"


class ResearchIdeaRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    raw_text: str
    created_by: uuid.UUID | None
    source: str
    created_at: datetime


class ResearchPlanCreate(BaseModel):
    project_id: uuid.UUID
    version: int
    provisional_title: str | None = None
    problem_statement: str | None = None
    objective: str | None = None
    scope_summary: str | None = None
    recommended_method: ResearchMethod | None = None
    recommended_framework: ResearchFrameworkType | None = None
    rationale: str | None = None
    created_by_agent_run_id: uuid.UUID | None = None


class ResearchPlanRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    status: ResearchPlanStatus
    provisional_title: str | None
    problem_statement: str | None
    objective: str | None
    scope_summary: str | None
    recommended_method: ResearchMethod | None
    recommended_framework: ResearchFrameworkType | None
    rationale: str | None
    created_by_agent_run_id: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime


class ResearchQuestionCreate(BaseModel):
    project_id: uuid.UUID
    research_plan_id: uuid.UUID
    question_type: str
    question_text: str
    is_primary: bool = False
    position: int = 0


class ResearchQuestionRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    research_plan_id: uuid.UUID
    question_type: str
    question_text: str
    is_primary: bool
    position: int
    status: str
    created_at: datetime


class ResearchFrameworkCreate(BaseModel):
    project_id: uuid.UUID
    framework_type: ResearchFrameworkType
    version: int = 1
    structured_elements: dict[str, object] = {}
    rationale: str | None = None


class ResearchFrameworkRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    framework_type: ResearchFrameworkType
    version: int
    structured_elements: dict[str, object]
    rationale: str | None
    created_at: datetime

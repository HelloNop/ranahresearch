import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import ProjectMemberRole
from ranah_domain.schemas.common import OrmModel


class OrganizationCreate(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class OrganizationRead(OrmModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    status: str
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    organization_id: uuid.UUID
    email: str
    display_name: str
    auth_provider: str
    provider_subject: str


class UserRead(OrmModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    display_name: str
    status: str
    auth_provider: str
    created_at: datetime
    updated_at: datetime


class ProjectMemberCreate(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: ProjectMemberRole


class ProjectMemberRead(OrmModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: ProjectMemberRole
    created_at: datetime

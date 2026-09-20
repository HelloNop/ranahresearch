import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import ProjectEventActorType
from ranah_domain.schemas.common import OrmModel


class ProjectEventCreate(BaseModel):
    project_id: uuid.UUID
    event_type: str
    actor_type: ProjectEventActorType
    actor_id: uuid.UUID | None = None
    payload: dict[str, object] = {}


class ProjectEventRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    actor_type: ProjectEventActorType
    actor_id: uuid.UUID | None
    payload: dict[str, object]
    created_at: datetime


class UsageEventCreate(BaseModel):
    organization_id: uuid.UUID
    user_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    event_type: str
    quantity: float
    unit: str
    cost_estimate: float | None = None
    provider: str | None = None


class UsageEventRead(OrmModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    project_id: uuid.UUID | None
    event_type: str
    quantity: float
    unit: str
    cost_estimate: float | None
    provider: str | None
    created_at: datetime

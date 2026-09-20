import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import WorkflowRunStatus
from ranah_domain.schemas.common import OrmModel


class WorkflowRunCreate(BaseModel):
    project_id: uuid.UUID
    temporal_workflow_id: str
    workflow_type: str


class WorkflowRunRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    temporal_workflow_id: str
    workflow_type: str
    status: WorkflowRunStatus
    started_at: datetime
    completed_at: datetime | None

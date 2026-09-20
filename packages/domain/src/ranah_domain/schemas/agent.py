import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import AgentDefinitionStatus, AgentRunStatus
from ranah_domain.schemas.common import OrmModel


class AgentDefinitionCreate(BaseModel):
    name: str
    version: str
    description: str | None = None
    input_schema: dict[str, object] = {}
    output_schema: dict[str, object] = {}
    prompt_version: str | None = None


class AgentDefinitionRead(OrmModel):
    id: uuid.UUID
    name: str
    version: str
    description: str | None
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    prompt_version: str | None
    status: AgentDefinitionStatus
    created_at: datetime


class AgentRunCreate(BaseModel):
    project_id: uuid.UUID
    agent_definition_id: uuid.UUID
    workflow_id: str | None = None
    task_type: str
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    input_metadata: dict[str, object] = {}


class AgentRunComplete(BaseModel):
    status: AgentRunStatus
    output_metadata: dict[str, object] = {}
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    error_code: str | None = None


class AgentRunRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    agent_definition_id: uuid.UUID
    workflow_id: str | None
    task_type: str
    status: AgentRunStatus
    model_provider: str | None
    model_name: str | None
    prompt_version: str | None
    input_metadata: dict[str, object]
    output_metadata: dict[str, object]
    started_at: datetime
    completed_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: float | None
    error_code: str | None

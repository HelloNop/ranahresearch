import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import SearchArtifactStatus, SearchRunStatus
from ranah_domain.schemas.common import OrmModel


class SearchStrategyCreate(BaseModel):
    project_id: uuid.UUID
    protocol_id: uuid.UUID | None = None
    version: int = 1
    description: str | None = None


class SearchStrategyRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    protocol_id: uuid.UUID | None
    version: int
    status: SearchArtifactStatus
    description: str | None
    created_at: datetime
    approved_at: datetime | None


class SearchQueryCreate(BaseModel):
    search_strategy_id: uuid.UUID
    provider: str
    query_text: str
    filters: dict[str, object] = {}
    version: int = 1


class SearchQueryRead(OrmModel):
    id: uuid.UUID
    search_strategy_id: uuid.UUID
    provider: str
    query_text: str
    filters: dict[str, object]
    version: int
    status: SearchArtifactStatus
    created_at: datetime


class SearchRunCreate(BaseModel):
    project_id: uuid.UUID
    search_query_id: uuid.UUID
    provider: str
    executed_query: str
    executed_filters: dict[str, object] = {}
    agent_run_id: uuid.UUID | None = None


class SearchRunRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    search_query_id: uuid.UUID
    provider: str
    executed_query: str
    executed_filters: dict[str, object]
    started_at: datetime | None
    completed_at: datetime | None
    result_count_reported: int | None
    result_count_retrieved: int
    status: SearchRunStatus
    provider_metadata: dict[str, object]
    agent_run_id: uuid.UUID | None
    created_at: datetime


class SearchResultCreate(BaseModel):
    search_run_id: uuid.UUID
    provider_record_id: str
    rank: int | None = None
    raw_payload_location: str | None = None
    normalized_payload: dict[str, object] | None = None


class SearchResultRead(OrmModel):
    id: uuid.UUID
    search_run_id: uuid.UUID
    provider_record_id: str
    rank: int | None
    raw_payload_location: str | None
    normalized_payload: dict[str, object] | None
    retrieved_at: datetime

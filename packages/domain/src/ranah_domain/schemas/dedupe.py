import uuid
from datetime import datetime

from pydantic import BaseModel

from ranah_domain.enums import DuplicateDecisionType, DuplicateGroupStatus, DuplicateGroupType
from ranah_domain.schemas.common import OrmModel


class DuplicateGroupCreate(BaseModel):
    project_id: uuid.UUID
    duplicate_type: DuplicateGroupType


class DuplicateGroupRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    duplicate_type: DuplicateGroupType
    status: DuplicateGroupStatus
    created_at: datetime
    resolved_at: datetime | None


class DuplicateMemberCreate(BaseModel):
    duplicate_group_id: uuid.UUID
    work_id: uuid.UUID
    similarity_score: float | None = None
    signals: dict[str, object] | None = None


class DuplicateMemberRead(OrmModel):
    id: uuid.UUID
    duplicate_group_id: uuid.UUID
    work_id: uuid.UUID
    similarity_score: float | None
    signals: dict[str, object] | None


class DuplicateDecisionCreate(BaseModel):
    duplicate_group_id: uuid.UUID
    canonical_work_id: uuid.UUID | None = None
    decision: DuplicateDecisionType
    reason: str | None = None
    resolved_by: str | None = None


class DuplicateDecisionRead(OrmModel):
    id: uuid.UUID
    duplicate_group_id: uuid.UUID
    canonical_work_id: uuid.UUID | None
    decision: DuplicateDecisionType
    reason: str | None
    resolved_by: str | None
    created_at: datetime

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from ranah_domain.enums import WorkIdentifierType, WorkVerificationStatus, WorkVerificationType
from ranah_domain.schemas.common import OrmModel


class WorkRecordCreate(BaseModel):
    project_id: uuid.UUID
    doi: str | None = None
    title: str
    abstract: str | None = None
    publication_year: int | None = None
    publication_date: date | None = None
    publication_type: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publisher: str | None = None
    language: str | None = None
    url: str | None = None
    open_access_status: str | None = None


class WorkRecordRead(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    doi: str | None
    title: str
    abstract: str | None
    publication_year: int | None
    publication_date: date | None
    publication_type: str | None
    journal: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    publisher: str | None
    language: str | None
    url: str | None
    open_access_status: str | None
    created_at: datetime
    updated_at: datetime


class WorkIdentifierCreate(BaseModel):
    work_id: uuid.UUID
    provider: str
    identifier_type: WorkIdentifierType
    identifier: str
    url: str | None = None


class WorkIdentifierRead(OrmModel):
    id: uuid.UUID
    work_id: uuid.UUID
    provider: str
    identifier_type: WorkIdentifierType
    identifier: str
    url: str | None


class WorkMetadataObservationCreate(BaseModel):
    work_id: uuid.UUID
    provider: str
    field_name: str
    field_value: dict[str, object]


class WorkMetadataObservationRead(OrmModel):
    id: uuid.UUID
    work_id: uuid.UUID
    provider: str
    field_name: str
    field_value: dict[str, object]
    observed_at: datetime


class WorkVerificationCreate(BaseModel):
    work_id: uuid.UUID
    verification_type: WorkVerificationType
    status: WorkVerificationStatus
    verified_by: str | None = None
    details: dict[str, object] | None = None


class WorkVerificationRead(OrmModel):
    id: uuid.UUID
    work_id: uuid.UUID
    verification_type: WorkVerificationType
    status: WorkVerificationStatus
    verified_by: str | None
    details: dict[str, object] | None
    verified_at: datetime

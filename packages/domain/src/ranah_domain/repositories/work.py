import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_domain.models.work import (
    WorkIdentifier,
    WorkMetadataObservation,
    WorkRecord,
    WorkVerification,
)
from ranah_domain.schemas.work import (
    WorkIdentifierCreate,
    WorkMetadataObservationCreate,
    WorkRecordCreate,
    WorkVerificationCreate,
)


async def create_work_record(session: AsyncSession, data: WorkRecordCreate) -> WorkRecord:
    work = WorkRecord(**data.model_dump())
    session.add(work)
    await session.flush()
    return work


async def get_by_doi(session: AsyncSession, project_id: uuid.UUID, doi: str) -> WorkRecord | None:
    stmt = select(WorkRecord).where(WorkRecord.project_id == project_id, WorkRecord.doi == doi)
    return (await session.scalars(stmt)).first()


async def get_by_identifier(
    session: AsyncSession, project_id: uuid.UUID, provider: str, identifier: str
) -> WorkRecord | None:
    """Finds a WorkRecord by a (provider, identifier) pair already recorded against it,
    scoped to the project. Used for idempotent re-ingestion when no DOI is available."""
    stmt = (
        select(WorkRecord)
        .join(WorkIdentifier, WorkIdentifier.work_id == WorkRecord.id)
        .where(
            WorkRecord.project_id == project_id,
            WorkIdentifier.provider == provider,
            WorkIdentifier.identifier == identifier,
        )
    )
    return (await session.scalars(stmt)).first()


async def identifier_exists(
    session: AsyncSession, work_id: uuid.UUID, provider: str, identifier: str
) -> bool:
    stmt = select(WorkIdentifier.id).where(
        WorkIdentifier.work_id == work_id,
        WorkIdentifier.provider == provider,
        WorkIdentifier.identifier == identifier,
    )
    return (await session.scalars(stmt)).first() is not None


async def add_identifier(session: AsyncSession, data: WorkIdentifierCreate) -> WorkIdentifier:
    identifier = WorkIdentifier(**data.model_dump())
    session.add(identifier)
    await session.flush()
    return identifier


async def add_metadata_observation(
    session: AsyncSession, data: WorkMetadataObservationCreate
) -> WorkMetadataObservation:
    observation = WorkMetadataObservation(**data.model_dump())
    session.add(observation)
    await session.flush()
    return observation


async def list_metadata_observations(
    session: AsyncSession, work_id: uuid.UUID
) -> list[WorkMetadataObservation]:
    stmt = select(WorkMetadataObservation).where(WorkMetadataObservation.work_id == work_id)
    return list((await session.scalars(stmt)).all())


async def add_verification(session: AsyncSession, data: WorkVerificationCreate) -> WorkVerification:
    verification = WorkVerification(**data.model_dump())
    session.add(verification)
    await session.flush()
    return verification

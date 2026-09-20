"""Bridges the DB-free literature engine (normalization/dedup/verification) into
ranah_domain persistence. This is the one module in this package allowed to know
about our Postgres schema - providers/models/http/normalization/deduplication/
verification stay independently testable without a database.
"""

import uuid

from ranah_domain.enums import DuplicateDecisionType, DuplicateGroupType, WorkIdentifierType
from ranah_domain.models.dedupe import DuplicateGroup
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord, WorkVerification
from ranah_domain.repositories import dedupe as dedupe_repo
from ranah_domain.repositories import work as work_repo
from ranah_domain.schemas.dedupe import (
    DuplicateDecisionCreate,
    DuplicateGroupCreate,
    DuplicateMemberCreate,
)
from ranah_domain.schemas.work import (
    WorkIdentifierCreate,
    WorkMetadataObservationCreate,
    WorkRecordCreate,
    WorkVerificationCreate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_literature.deduplication import DuplicateMatch, decision_for_tier
from ranah_literature.models import ProviderIdentifierType
from ranah_literature.normalization import CanonicalWorkCandidate
from ranah_literature.verification import VerificationOutcome

_IDENTIFIER_TYPE_MAP: dict[ProviderIdentifierType, WorkIdentifierType] = {
    ProviderIdentifierType.DOI: WorkIdentifierType.DOI,
    ProviderIdentifierType.OPENALEX_ID: WorkIdentifierType.OPENALEX_ID,
    ProviderIdentifierType.SEMANTIC_SCHOLAR_ID: WorkIdentifierType.SEMANTIC_SCHOLAR_ID,
    ProviderIdentifierType.PMID: WorkIdentifierType.PMID,
    ProviderIdentifierType.PMCID: WorkIdentifierType.PMCID,
    ProviderIdentifierType.ARXIV_ID: WorkIdentifierType.ARXIV_ID,
}


async def persist_canonical_work(
    session: AsyncSession, project_id: uuid.UUID, candidate: CanonicalWorkCandidate
) -> WorkRecord:
    """Idempotent: re-ingesting the same publication (by DOI, or by any provider
    identifier already on file) returns the existing WorkRecord rather than
    creating a duplicate canonical row (EPIC-010 #28)."""
    existing: WorkRecord | None = None
    if candidate.doi:
        existing = await work_repo.get_by_doi(session, project_id, candidate.doi)
    if existing is None:
        for source in candidate.source_works:
            for identifier in source.identifiers:
                existing = await work_repo.get_by_identifier(
                    session, project_id, source.provider, identifier.identifier
                )
                if existing is not None:
                    break
            if existing is not None:
                break

    if existing is None:
        for source in candidate.source_works:
            if not source.provider_id:
                continue
            existing = await session.scalar(
                select(WorkRecord)
                .join(WorkMetadataObservation)
                .where(
                    WorkRecord.project_id == project_id,
                    WorkMetadataObservation.provider == source.provider,
                    WorkMetadataObservation.field_name == "provider_record_id",
                    WorkMetadataObservation.field_value == {"value": source.provider_id},
                )
                .limit(1)
            )
            if existing is not None:
                break

    if existing is None:
        existing = await work_repo.create_work_record(
            session,
            WorkRecordCreate(
                project_id=project_id,
                doi=candidate.doi,
                title=candidate.title,
                abstract=candidate.abstract,
                publication_year=candidate.publication_year,
                publication_type=candidate.work_type,
                journal=candidate.venue,
                volume=candidate.volume,
                issue=candidate.issue,
                pages=candidate.pages,
                publisher=candidate.publisher,
                url=candidate.url,
            ),
        )

    for source in candidate.source_works:
        await work_repo.add_metadata_observation(
            session,
            WorkMetadataObservationCreate(
                work_id=existing.id,
                provider=source.provider,
                field_name="provider_record_id",
                field_value={"value": source.provider_id},
            ),
        )
        for identifier in source.identifiers:
            if await work_repo.identifier_exists(
                session, existing.id, source.provider, identifier.identifier
            ):
                continue
            await work_repo.add_identifier(
                session,
                WorkIdentifierCreate(
                    work_id=existing.id,
                    provider=source.provider,
                    identifier_type=_IDENTIFIER_TYPE_MAP[identifier.identifier_type],
                    identifier=identifier.identifier,
                    url=identifier.url,
                ),
            )

    for observation in candidate.observations:
        await work_repo.add_metadata_observation(
            session,
            WorkMetadataObservationCreate(
                work_id=existing.id,
                provider=observation.provider,
                field_name=observation.field_name,
                field_value={"value": observation.value},
            ),
        )

    return existing


_SIGNAL_TO_GROUP_TYPE = {
    "exact_doi": DuplicateGroupType.EXACT_DOI,
    "exact_external_id": DuplicateGroupType.EXTERNAL_ID,
    "exact_title": DuplicateGroupType.EXACT_TITLE,
    "fuzzy_title": DuplicateGroupType.FUZZY_TITLE,
}


def _duplicate_group_type(match: DuplicateMatch) -> DuplicateGroupType:
    signal = match.signals.get("signal")
    if isinstance(signal, str) and signal in _SIGNAL_TO_GROUP_TYPE:
        return _SIGNAL_TO_GROUP_TYPE[signal]
    return DuplicateGroupType.POTENTIAL_DUPLICATE


async def persist_duplicate_match(
    session: AsyncSession,
    project_id: uuid.UUID,
    match: DuplicateMatch,
    work_id_a: uuid.UUID,
    work_id_b: uuid.UUID,
) -> DuplicateGroup:
    """Idempotent: re-running dedup on the same pair reuses the existing group
    instead of creating a second one. Never deletes anything (EPIC-011 #15)."""
    existing = await dedupe_repo.find_group_containing_pair(session, work_id_a, work_id_b)
    if existing is not None:
        return existing

    group = await dedupe_repo.create_group(
        session,
        DuplicateGroupCreate(project_id=project_id, duplicate_type=_duplicate_group_type(match)),
    )
    for work_id in (work_id_a, work_id_b):
        await dedupe_repo.add_member(
            session,
            DuplicateMemberCreate(
                duplicate_group_id=group.id,
                work_id=work_id,
                similarity_score=match.score,
                signals=match.signals,
            ),
        )
    decision_type = decision_for_tier(match.tier)
    await dedupe_repo.record_decision(
        session,
        DuplicateDecisionCreate(
            duplicate_group_id=group.id,
            canonical_work_id=work_id_a if decision_type == DuplicateDecisionType.MERGE else None,
            decision=decision_type,
            reason=f"tier={match.tier.value}, signals={match.signals}",
            resolved_by="system:deduplication_v1",
        ),
    )
    return group


async def persist_verification(
    session: AsyncSession, work_id: uuid.UUID, outcome: VerificationOutcome
) -> WorkVerification:
    return await work_repo.add_verification(
        session,
        WorkVerificationCreate(
            work_id=work_id,
            verification_type=outcome.verification_type,
            status=outcome.status,
            verified_by="system:source_verification_v1",
            details={
                "confirmed_by": outcome.confirmed_by,
                "conflicts": outcome.conflicts,
                "outages": [{"provider": o.provider, "reason": o.reason} for o in outcome.outages],
                **outcome.details,
            },
        ),
    )

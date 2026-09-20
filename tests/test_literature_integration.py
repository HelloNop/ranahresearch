"""EPIC-009 through EPIC-012 integration test:

    fake/fixture provider search -> normalization -> dedupe -> verification
    -> persisted WorkRecords

Asserts the key provenance relationships (search run -> results -> work
records -> identifiers -> observations -> duplicate decisions ->
verifications) and that re-running the same search does not create
uncontrolled duplicate canonical works (EPIC-010 #28 idempotency).
"""

import uuid

from ranah_domain.enums import DuplicateDecisionType, WorkVerificationStatus
from ranah_domain.models.dedupe import DuplicateDecision
from ranah_domain.repositories import organizations as organizations_repo
from ranah_domain.repositories import projects as projects_repo
from ranah_domain.repositories import search as search_repo
from ranah_domain.repositories import work as work_repo
from ranah_domain.schemas.organization import OrganizationCreate
from ranah_domain.schemas.project import ResearchProjectCreate
from ranah_domain.schemas.search import SearchQueryCreate, SearchStrategyCreate
from ranah_literature.discovery import LiteratureDiscoveryService
from ranah_literature.models import (
    ProviderIdentifier,
    ProviderIdentifierType,
    ProviderWork,
    SearchRequest,
)
from ranah_literature.providers.fake import FakeAcademicProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _project(session: AsyncSession) -> uuid.UUID:
    org = await organizations_repo.create_organization(
        session, OrganizationCreate(name="Lit test org", slug=f"lit-{uuid.uuid4().hex[:8]}")
    )
    project = await projects_repo.create_project(
        session, ResearchProjectCreate(organization_id=org.id, title="Lit test project")
    )
    return project.id


async def _search_query(session: AsyncSession, project_id: uuid.UUID) -> uuid.UUID:
    strategy = await search_repo.create_strategy(
        session, SearchStrategyCreate(project_id=project_id)
    )
    query = await search_repo.create_query(
        session,
        SearchQueryCreate(
            search_strategy_id=strategy.id, provider="multi", query_text="generative ai education"
        ),
    )
    return query.id


def _same_paper_from_two_providers() -> tuple[ProviderWork, ProviderWork]:
    doi = "10.1000/same-paper"
    crossref_version = ProviderWork(
        provider="crossref",
        provider_id=doi,
        doi=doi,
        title="Generative AI in Higher Education",
        publication_year=2024,
        identifiers=[
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi)
        ],
    )
    openalex_version = ProviderWork(
        provider="openalex",
        provider_id="W1",
        doi=doi,
        title="Generative AI in Higher Education: Learning Outcomes",
        abstract="A longer OpenAlex abstract describing the study.",
        publication_year=2024,
        identifiers=[
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi),
            ProviderIdentifier(identifier_type=ProviderIdentifierType.OPENALEX_ID, identifier="W1"),
        ],
    )
    return crossref_version, openalex_version


def _unrelated_paper() -> ProviderWork:
    # Shares the broad query term with the other two but is a genuinely different
    # study (different DOI, topic, year) - it must not be merged or deduped with them.
    return ProviderWork(
        provider="semantic_scholar",
        provider_id="s2-unrelated",
        doi="10.1000/unrelated",
        title="Generative AI Adoption in Veterinary Cat Clinics",
        publication_year=2019,
        identifiers=[
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.SEMANTIC_SCHOLAR_ID,
                identifier="s2-unrelated",
            )
        ],
    )


async def test_full_discovery_pipeline_persists_provenance(db_session: AsyncSession) -> None:
    project_id = await _project(db_session)
    search_query_id = await _search_query(db_session, project_id)

    crossref_work, openalex_work = _same_paper_from_two_providers()
    unrelated = _unrelated_paper()

    providers = {
        "crossref": FakeAcademicProvider([crossref_work], name="crossref"),
        "openalex": FakeAcademicProvider([openalex_work], name="openalex"),
        "semantic_scholar": FakeAcademicProvider([unrelated], name="semantic_scholar"),
    }
    service = LiteratureDiscoveryService(db_session, providers)
    report = await service.run(project_id, search_query_id, SearchRequest(query="generative ai"))

    # Every provider actually ran a SearchRun with SearchResults, even the one
    # whose result doesn't match the other two (docs #25/#26 provenance).
    assert {o.provider for o in report.provider_outcomes} == {
        "crossref",
        "openalex",
        "semantic_scholar",
    }
    assert all(o.error is None for o in report.provider_outcomes)

    # DOI-grouping merged the crossref+openalex records into ONE WorkRecord before
    # persistence; the unrelated paper is a second WorkRecord. Two total, not three.
    assert len(report.work_ids) == 2

    merged_record = await work_repo.get_by_doi(db_session, project_id, "10.1000/same-paper")
    assert merged_record is not None
    # The richer OpenAlex abstract won the merge; nothing was concatenated.
    assert merged_record.abstract == "A longer OpenAlex abstract describing the study."

    observations = await work_repo.list_metadata_observations(db_session, merged_record.id)
    assert {o.provider for o in observations} >= {"crossref", "openalex"}

    unrelated_record = await work_repo.get_by_doi(db_session, project_id, "10.1000/unrelated")
    assert unrelated_record is not None

    # No duplicate group between two genuinely different papers.
    assert report.duplicate_group_count == 0

    # Both persisted works got a DOI verification outcome.
    assert report.verification_status_counts
    for status in report.verification_status_counts:
        assert status in {s.value for s in WorkVerificationStatus}


async def test_rerunning_same_search_is_idempotent(db_session: AsyncSession) -> None:
    project_id = await _project(db_session)
    search_query_id = await _search_query(db_session, project_id)
    crossref_work, openalex_work = _same_paper_from_two_providers()

    providers = {
        "crossref": FakeAcademicProvider([crossref_work], name="crossref"),
        "openalex": FakeAcademicProvider([openalex_work], name="openalex"),
    }
    service = LiteratureDiscoveryService(db_session, providers)
    request = SearchRequest(query="generative ai")

    first = await service.run(project_id, search_query_id, request)
    second = await service.run(project_id, search_query_id, request)

    # Two SearchRun histories exist (rerun is visible)...
    strategy_runs_first = first.provider_outcomes
    strategy_runs_second = second.provider_outcomes
    assert len(strategy_runs_first) == len(strategy_runs_second) == 2

    # ...but canonical WorkRecords did not double: same DOI resolves to the same row.
    all_doi_records = [
        await work_repo.get_by_doi(db_session, project_id, "10.1000/same-paper") for _ in range(2)
    ]
    assert all_doi_records[0] is not None
    assert all_doi_records[1] is not None
    assert all_doi_records[0].id == all_doi_records[1].id
    assert first.work_ids == second.work_ids


async def test_conflicting_doi_same_title_dedup_is_review_required(
    db_session: AsyncSession,
) -> None:
    project_id = await _project(db_session)
    search_query_id = await _search_query(db_session, project_id)

    work_a = ProviderWork(
        provider="crossref",
        provider_id="10.1/aaa",
        doi="10.1/aaa",
        title="A study of things",
        publication_year=2022,
    )
    work_b = ProviderWork(
        provider="openalex",
        provider_id="10.1/bbb",
        doi="10.1/bbb",
        title="A study of things",
        publication_year=2022,
    )
    providers = {
        "crossref": FakeAcademicProvider([work_a], name="crossref"),
        "openalex": FakeAcademicProvider([work_b], name="openalex"),
    }
    service = LiteratureDiscoveryService(db_session, providers)
    await service.run(project_id, search_query_id, SearchRequest(query="a study of things"))

    decisions = list((await db_session.scalars(select(DuplicateDecision))).all())
    assert len(decisions) == 1
    assert decisions[0].decision == DuplicateDecisionType.REVIEW_REQUIRED

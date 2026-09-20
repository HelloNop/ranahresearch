"""Developer-only literature discovery demo/smoke harness. Not product architecture.

    uv run --all-packages python scripts/literature_demo.py "generative AI learning outcomes"

By default this uses in-memory fixture providers: no network, no paid API, safe
to run anywhere `make infra-up` is running. Set RANAH_LIVE_PROVIDER_SMOKE=1 to
run against the real Crossref/OpenAlex/Semantic Scholar APIs instead (the
opt-in live smoke test from EPIC-012 #38) - never used by `make check`/CI.
"""

import asyncio
import os
import sys
import uuid

from ranah_domain.db import create_engine, create_session_factory, session_scope
from ranah_domain.repositories import organizations as organizations_repo
from ranah_domain.repositories import projects as projects_repo
from ranah_domain.repositories import search as search_repo
from ranah_domain.schemas.organization import OrganizationCreate
from ranah_domain.schemas.project import ResearchProjectCreate
from ranah_domain.schemas.search import SearchQueryCreate, SearchStrategyCreate
from ranah_literature.discovery import LiteratureDiscoveryService
from ranah_literature.http import ProviderHTTPClient
from ranah_literature.models import (
    ProviderIdentifier,
    ProviderIdentifierType,
    ProviderWork,
    SearchRequest,
)
from ranah_literature.providers.base import AcademicProvider
from ranah_literature.providers.crossref import CrossrefProvider
from ranah_literature.providers.fake import FakeAcademicProvider
from ranah_literature.providers.openalex import OpenAlexProvider
from ranah_literature.providers.semantic_scholar import SemanticScholarProvider


def _fixture_providers() -> dict[str, AcademicProvider]:
    doi = "10.1000/demo-paper"
    crossref_work = ProviderWork(
        provider="crossref",
        provider_id=doi,
        doi=doi,
        title="Generative AI Learning Outcomes in Higher Education",
        publication_year=2024,
        identifiers=[
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi)
        ],
    )
    openalex_work = ProviderWork(
        provider="openalex",
        provider_id="W1",
        doi=doi,
        title="Generative AI Learning Outcomes in Higher Education",
        abstract="A demo abstract about generative AI in education.",
        publication_year=2024,
        identifiers=[
            ProviderIdentifier(identifier_type=ProviderIdentifierType.DOI, identifier=doi),
            ProviderIdentifier(identifier_type=ProviderIdentifierType.OPENALEX_ID, identifier="W1"),
        ],
    )
    s2_work = ProviderWork(
        provider="semantic_scholar",
        provider_id="s2demo",
        doi=None,
        title="Generative AI and Student Learning Outcomes",
        publication_year=2023,
        identifiers=[
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.SEMANTIC_SCHOLAR_ID, identifier="s2demo"
            )
        ],
    )
    return {
        "crossref": FakeAcademicProvider([crossref_work], name="crossref"),
        "openalex": FakeAcademicProvider([openalex_work], name="openalex"),
        "semantic_scholar": FakeAcademicProvider([s2_work], name="semantic_scholar"),
    }


def _live_providers() -> dict[str, AcademicProvider]:
    return {
        "crossref": CrossrefProvider(ProviderHTTPClient("https://api.crossref.org", max_retries=2)),
        "openalex": OpenAlexProvider(ProviderHTTPClient("https://api.openalex.org", max_retries=2)),
        "semantic_scholar": SemanticScholarProvider(
            ProviderHTTPClient("https://api.semanticscholar.org/graph/v1", max_retries=2)
        ),
    }


async def main() -> None:
    query = " ".join(sys.argv[1:]) or "generative AI learning outcomes higher education"
    live = os.environ.get("RANAH_LIVE_PROVIDER_SMOKE") == "1"
    providers = _live_providers() if live else _fixture_providers()

    print(f"query: {query!r}")
    print(f"mode: {'LIVE (real network APIs)' if live else 'fixture (no network)'}")

    engine = create_engine()
    session_factory = create_session_factory(engine)
    async with session_scope(session_factory) as session:
        org = await organizations_repo.create_organization(
            session,
            OrganizationCreate(name="Literature demo org", slug=f"demo-{uuid.uuid4().hex[:8]}"),
        )
        project = await projects_repo.create_project(
            session, ResearchProjectCreate(organization_id=org.id, title="Literature demo project")
        )
        strategy = await search_repo.create_strategy(
            session, SearchStrategyCreate(project_id=project.id)
        )
        search_query = await search_repo.create_query(
            session,
            SearchQueryCreate(search_strategy_id=strategy.id, provider="multi", query_text=query),
        )

        service = LiteratureDiscoveryService(session, providers)
        report = await service.run(
            project.id, search_query.id, SearchRequest(query=query, page_size=5)
        )

    for outcome in report.provider_outcomes:
        status = f"ERROR: {outcome.error}" if outcome.error else "ok"
        line = f"{outcome.provider} retrieved: {outcome.retrieved} (reported: {outcome.reported})"
        print(f"{line} [{status}]")
    print(f"Canonical works: {len(report.work_ids)}")
    print(f"Duplicate groups: {report.duplicate_group_count}")
    print(f"Verification status counts: {report.verification_status_counts}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

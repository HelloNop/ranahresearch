import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.discovery_activities as discovery
import ranah_worker_orchestration.research_activities as planning
from pydantic import ValidationError
from ranah_agents.research import FrameworkOutput, PlanOutput, StrategyOutput
from ranah_api.main import app
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.models.agent import AgentRun
from ranah_domain.models.dedupe import DuplicateDecision, DuplicateGroup
from ranah_domain.models.events import ProjectEvent
from ranah_domain.models.organization import Organization, User
from ranah_domain.models.project import ResearchIdea, ResearchPlan
from ranah_domain.models.search import SearchResult, SearchRun
from ranah_domain.models.work import WorkRecord, WorkVerification
from ranah_literature.errors import ProviderResponseError
from ranah_literature.models import (
    ProviderIdentifier,
    ProviderIdentifierType,
    ProviderWork,
    SearchPage,
    SearchRequest,
)
from ranah_literature.providers.fake import FakeAcademicProvider
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import StructuredGenerateRequest
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from ranah_worker_orchestration.research_workflows import (
    ResearchDiscoveryWorkflow,
    ResearchPlanningWorkflow,
)
from ranah_workflow import connect_client
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.worker import Worker

PLAN: dict[str, Any] = {
    "provisional_title": "Generative AI and university learning",
    "problem_statement": "The effects on learning need assessment.",
    "research_objective": "Map reported learning outcomes.",
    "candidate_research_questions": ["How is generative AI used in university learning?"],
    "recommended_research_question": "How is generative AI used in university learning?",
    "recommended_review_method": "SCOPING_REVIEW",
    "recommended_framework": "PCC",
    "scope": "Higher education",
    "key_concepts": ["generative AI", "learning"],
    "assumptions": [],
    "uncertainties": ["Literature discovery is required to validate scope."],
    "rationale": "A candidate direction for mapping a broad question, not a novelty claim.",
}
FRAMEWORK: dict[str, Any] = {
    "framework_type": "PCC",
    "elements": [
        {"name": "population", "values": ["University students"]},
        {"name": "concept", "values": ["Generative AI learning"]},
        {"name": "context", "values": ["Higher education"]},
    ],
    "missing_elements": [],
    "rationale": "A mapping question",
    "confidence": 0.8,
}
STRATEGY: dict[str, Any] = {
    "concepts": [{"label": "AI", "terms": ["generative AI", "ChatGPT"]}],
    "provider_queries": [
        {"provider": provider, "query_text": "generative AI", "rationale": "Broad discovery"}
        for provider in ("crossref", "openalex", "semantic_scholar")
    ],
    "filters": {"year_from": None, "year_to": None},
    "rationale": "Broad discovery before a protocol",
    "known_limitations": ["Bounded discovery"],
}


def llm_response(request: StructuredGenerateRequest) -> dict[str, Any]:
    return {"PlanOutput": PLAN, "FrameworkOutput": FRAMEWORK, "StrategyOutput": STRATEGY}[
        request.schema_name
    ]


class FixtureProvider(FakeAcademicProvider):
    def __init__(self, name: str, mode: str) -> None:
        works = (
            []
            if mode == "zero"
            else [
                ProviderWork(
                    provider=name,
                    provider_id=f"{name}-1",
                    doi="10.1234/ai",
                    title="Generative AI in university learning",
                    publication_year=2024,
                    identifiers=[
                        ProviderIdentifier(
                            identifier_type=ProviderIdentifierType.DOI, identifier="10.1234/ai"
                        )
                    ],
                )
            ]
        )
        if name == "openalex" and mode != "zero":
            works.append(
                ProviderWork(
                    provider=name,
                    provider_id="W2",
                    title="Generative AI in university learning",
                    publication_year=2024,
                    identifiers=[
                        ProviderIdentifier(
                            identifier_type=ProviderIdentifierType.OPENALEX_ID, identifier="W2"
                        )
                    ],
                )
            )
        super().__init__(works, name=name)
        self.mode = mode
        self.attempts = 0

    async def search(self, request: SearchRequest) -> SearchPage:
        self.attempts += 1
        if self.name == "crossref" and (
            self.mode == "partial" or (self.mode == "transient" and self.attempts == 1)
        ):
            raise ProviderResponseError("fixture Crossref outage")
        return await super().search(request)

    async def get_by_doi(self, doi: str) -> ProviderWork | None:
        work = await super().get_by_doi(doi)
        if work and self.mode == "conflict" and self.name == "crossref":
            return work.model_copy(update={"title": "Conflicting provider title"})
        return work


@pytest.fixture
async def api_client(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    from ranah_api import projects
    from ranah_worker_orchestration import activities

    factory = create_session_factory(db_engine)
    monkeypatch.setattr(projects, "session_factory", lambda: factory)
    monkeypatch.setattr(activities, "_session_factory", lambda: factory)
    monkeypatch.setattr(planning, "_session_factory", lambda: factory)
    monkeypatch.setattr(discovery, "_session_factory", lambda: factory)
    async with session_scope(factory) as session:
        org = Organization(name="Slice fixtures", slug=uuid.uuid4().hex)
        session.add(org)
        await session.flush()
        user = User(
            organization_id=org.id,
            email=f"{uuid.uuid4()}@example.test",
            display_name="Fixture researcher",
            auth_provider="fixture",
            provider_subject=uuid.uuid4().hex,
        )
        session.add(user)
        await session.flush()
        monkeypatch.setenv("RANAH_API_TOKENS", json.dumps({"fixture-token": str(user.id)}))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer fixture-token"},
    ) as client:
        yield client


async def test_project_api_scope(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = await api_client.post("/projects", json={"idea": "An initial idea"})
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    assert response.json()["status"] == "IDEA"
    assert (await api_client.get(f"/projects/{project_id}")).status_code == 200
    assert (
        await api_client.post(f"/projects/{project_id}/ideas", json={"idea": "Refined idea"})
    ).status_code == 201
    assert (await api_client.get(f"/projects/{uuid.uuid4()}")).status_code == 404
    assert (await api_client.post("/projects", json={"idea": "   "})).status_code == 422
    async with session_scope(create_session_factory(db_engine)) as session:
        other_org = Organization(name="Other tenant", slug=uuid.uuid4().hex)
        session.add(other_org)
        await session.flush()
        other_user = User(
            organization_id=other_org.id,
            email=f"{uuid.uuid4()}@example.test",
            display_name="Other",
            auth_provider="fixture",
            provider_subject=uuid.uuid4().hex,
        )
        session.add(other_user)
        await session.flush()
        monkeypatch.setenv("RANAH_API_TOKENS", json.dumps({"fixture-token": str(other_user.id)}))
    assert (await api_client.get(f"/projects/{project_id}")).status_code == 404
    assert (await api_client.get(f"/projects/{project_id}/events")).status_code == 404
    assert (await api_client.get("/projects")).json() == []
    assert (
        await api_client.get("/projects", headers={"Authorization": "Bearer wrong"})
    ).status_code == 401


@pytest.mark.parametrize("mode", ["success", "partial", "transient", "zero", "conflict", "invalid"])
async def test_discovery_vertical_slice(
    api_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    fake = FakeLLMProvider(
        structured_response_fn=(lambda _: {}) if mode == "invalid" else llm_response
    )
    gateway = LLMGateway(
        {"fake": fake},
        ModelRouter({ModelTier.STANDARD: RoutedModel(provider="fake", model="fixture-v1")}),
    )
    monkeypatch.setattr(planning, "gateway", lambda: gateway)
    providers = {
        name: FixtureProvider(name, mode) for name in ("crossref", "openalex", "semantic_scholar")
    }
    monkeypatch.setattr(discovery, "providers", lambda: providers)
    queue = f"slice-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue)
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[ResearchPlanningWorkflow, ResearchDiscoveryWorkflow],
        activities=[
            planning.set_operation_stage,
            planning.generate_research_artifact,
            planning.finish_operation,
            discovery.validate_discovery,
            discovery.execute_provider_search,
            discovery.record_provider_failure,
            discovery.normalize_discovery,
            discovery.deduplicate_discovery,
            discovery.verify_discovery,
            discovery.finalize_discovery,
        ],
    ):
        response = await api_client.post(
            "/projects", json={"idea": "Pengaruh generative AI pada hasil belajar"}
        )
        assert response.status_code == 201, response.text
        project_id = response.json()["id"]
        base = f"/projects/{project_id}"
        assert (
            await api_client.post(base + "/search-strategy/generate", json={})
        ).status_code == 409

        async def command(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
            response = await api_client.post(base + path, json=body)
            assert response.status_code == 202, response.text
            op_id = response.json()["operation_id"]
            await temporal.get_workflow_handle(f"research-{op_id}").result()
            return cast(
                dict[str, Any], (await api_client.get(base + f"/operations/{op_id}")).json()
            )

        op = await command("/plan/generate")
        if mode == "invalid":
            assert op["status"] == "FAILED"
            assert len(fake.calls) == 3
            assert (await api_client.get(base + "/plan")).json() is None
            async with session_scope(create_session_factory(db_engine)) as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ResearchIdea)
                        .where(ResearchIdea.project_id == uuid.UUID(project_id))
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(AgentRun.status).where(AgentRun.project_id == uuid.UUID(project_id))
                    )
                    == "FAILED"
                )
            return
        assert op["status"] == "COMPLETED", op
        plan = (await api_client.get(base + "/plan")).json()
        assert plan["content"]["recommended_review_method"] == "SCOPING_REVIEW"
        assert plan["created_by_agent_run_id"]
        assert (await api_client.get(base + "/framework")).json()["structured_elements"][
            "framework_type"
        ] == "PCC"
        assert (
            await api_client.post(base + "/plan/approve", json={"plan_id": plan["id"]})
        ).status_code == 200
        assert (await command("/search-strategy/generate", {}))["status"] == "COMPLETED"
        assert sum(p.attempts for p in providers.values()) == 0
        op = await command("/literature/search")
        assert op["status"] == ("PARTIAL" if mode == "partial" else "COMPLETED"), op
        works = (await api_client.get(base + "/literature")).json()
        assert len(works) == (0 if mode == "zero" else 2), works
        if mode == "transient":
            assert providers["crossref"].attempts == 2
        if mode == "conflict":
            assert any(work["verification_status"] == "CONFLICT" for work in works)
        if mode == "partial":
            assert any(run["status"] == "FAILED" for run in op["provider_runs"])
        await command("/literature/search")
        assert len((await api_client.get(base + "/literature")).json()) == len(works)
        async with session_scope(create_session_factory(db_engine)) as session:
            pid = uuid.UUID(project_id)
            runs = list(await session.scalars(select(SearchRun).where(SearchRun.project_id == pid)))
            assert len(runs) == 6
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchPlan)
                    .where(ResearchPlan.project_id == pid)
                )
                == 1
            )
            agent_runs = list(
                await session.scalars(select(AgentRun).where(AgentRun.project_id == pid))
            )
            assert len(agent_runs) == 3
            assert all(
                run.model_provider == "fake" and run.input_tokens == 10 for run in agent_runs
            )
            if mode != "zero":
                assert await session.scalar(
                    select(func.count())
                    .select_from(SearchResult)
                    .join(SearchRun)
                    .where(SearchRun.project_id == pid)
                )
                assert await session.scalar(
                    select(func.count())
                    .select_from(WorkVerification)
                    .join(WorkRecord)
                    .where(WorkRecord.project_id == pid)
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(DuplicateDecision)
                        .join(DuplicateGroup)
                        .where(DuplicateGroup.project_id == pid)
                    )
                    == 1
                )
                assert any(work["duplicate_status"] == "REVIEW_REQUIRED" for work in works)
            events = set(
                await session.scalars(
                    select(ProjectEvent.event_type).where(ProjectEvent.project_id == pid)
                )
            )
            assert {
                "RESEARCH_PLAN_GENERATED",
                "RESEARCH_PLAN_APPROVED",
                "FRAMEWORK_SELECTED",
                "SEARCH_STRATEGY_CREATED",
                "SOURCE_VERIFICATION_COMPLETED",
                "DISCOVERY_COMPLETED",
            } <= events


@pytest.mark.parametrize(
    "kind,names",
    [
        ("PICO", ["population", "intervention", "comparator", "outcomes"]),
        ("PICOS", ["population", "intervention", "comparator", "outcomes", "study_design"]),
        ("PCC", ["population", "concept", "context"]),
        ("SPIDER", ["sample", "phenomenon_of_interest", "design", "evaluation", "research_type"]),
        ("CUSTOM", ["topic"]),
    ],
)
def test_framework_contract(kind: str, names: list[str]) -> None:
    data = {
        **FRAMEWORK,
        "framework_type": kind,
        "elements": [{"name": name, "values": ["Specified"]} for name in names[:-1]],
        "missing_elements": names[-1:],
    }
    if kind == "CUSTOM":
        data["elements"] = [{"name": "topic", "values": ["Specified"]}]
    assert FrameworkOutput.model_validate(data).missing_elements == names[-1:]
    if kind != "CUSTOM":
        with pytest.raises(ValidationError):
            FrameworkOutput.model_validate({**data, "missing_elements": []})


def test_invalid_agent_contracts() -> None:
    with pytest.raises(ValidationError):
        PlanOutput.model_validate({**PLAN, "recommended_review_method": "invented"})
    with pytest.raises(ValidationError):
        StrategyOutput.model_validate({**STRATEGY, "provider_queries": []})


def test_openai_strict_output_schema() -> None:
    from ranah_llm.providers.openai import strict_schema

    schema = strict_schema(StrategyOutput.model_json_schema())
    filters = schema["$defs"]["SearchFilters"]
    assert set(filters["required"]) == {"year_from", "year_to"}
    assert filters["additionalProperties"] is False
    assert "default" not in filters["properties"]["year_from"]


async def test_project_scoped_identifiers_and_missing_doi(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    from ranah_domain.models.work import WorkIdentifier
    from ranah_literature.normalization import merge_provider_works
    from ranah_literature.persistence import persist_canonical_work

    project_ids = [
        (await api_client.post("/projects", json={"idea": "AI"})).json()["id"] for _ in range(2)
    ]
    record = ProviderWork(
        provider="crossref",
        provider_id="10.1234/shared",
        doi="10.1234/shared",
        title="Shared paper",
        identifiers=[
            ProviderIdentifier(
                identifier_type=ProviderIdentifierType.DOI, identifier="10.1234/shared"
            )
        ],
    )
    no_doi = ProviderWork(provider="fixture", provider_id="native-123", title="No DOI")
    async with session_scope(create_session_factory(db_engine)) as session:
        ids = []
        for project_id in project_ids:
            work = await persist_canonical_work(
                session, uuid.UUID(project_id), merge_provider_works([record])
            )
            ids.append(work.id)
            first = await persist_canonical_work(
                session, uuid.UUID(project_id), merge_provider_works([no_doi])
            )
            second = await persist_canonical_work(
                session, uuid.UUID(project_id), merge_provider_works([no_doi])
            )
            assert first.id == second.id
        assert ids[0] != ids[1]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(WorkIdentifier)
                .where(WorkIdentifier.work_id.in_(ids))
            )
            == 2
        )

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.study_activities as studies
from ranah_agents.studies import LinkCandidate, StudyLinkInput, StudyLinkOutput, validate_link
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.enums import StudyWorkRelationship
from ranah_domain.models.study import Study, StudyLinkDecision, StudyWork
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_literature.study_linking import (
    LinkTier,
    StudyCandidate,
    find_link_signals,
    find_registrations,
)
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import StructuredGenerateRequest
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.study_workflows import StudyLinkingWorkflow
from ranah_workflow import connect_client
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.worker import Worker
from test_research_slice import api_client as api_client
from test_screening_slice import CRITERION, PROTOCOL

TRIAL = "NCT12345678"


def test_registration_extraction() -> None:
    assert find_registrations(f"Registered as {TRIAL} on the registry.") == {TRIAL}
    assert find_registrations("ISRCTN87654321 and ACTRN12605000123456") == {
        "ISRCTN87654321",
        "ACTRN12605000123456",
    }
    # A bare number in prose is not a registration identifier.
    assert find_registrations("We enrolled 12345678 people, which would be a lot.") == set()


def candidate(work_id: str, **kwargs: Any) -> StudyCandidate:
    defaults: dict[str, Any] = {
        "title": "Generative AI tutoring in higher education",
        "abstract": "A randomised trial.",
        "authors": ("Sari, A.", "Budi, C."),
    }
    return StudyCandidate(work_id=work_id, **{**defaults, **kwargs})


def test_case_a_shared_registration_is_conclusive() -> None:
    signals = find_link_signals(
        [
            candidate("a", abstract=f"Trial {TRIAL}. Main results."),
            candidate("b", abstract=f"Conference abstract of {TRIAL}."),
        ]
    )
    assert len(signals) == 1
    assert signals[0].tier is LinkTier.REGISTRATION and signals[0].registration_id == TRIAL


def test_case_b_conference_abstract_is_a_candidate_not_a_conclusion() -> None:
    signals = find_link_signals(
        [
            candidate(
                "a", abstract="We randomised 214 students.", publication_type="journal-article"
            ),
            candidate(
                "b",
                abstract="Interim data on 214 students.",
                publication_type="conference-abstract",
            ),
        ]
    )
    assert signals and signals[0].tier is LinkTier.STRONG_CANDIDATE
    assert signals[0].signals["conference_abstract"] is True
    assert 214 in cast(list[int], signals[0].signals["shared_sample_sizes"])


def test_case_c_same_topic_different_sample_is_not_linked_deterministically() -> None:
    signals = find_link_signals(
        [
            candidate("a", abstract="We randomised 214 students.", authors=("Sari, A.",)),
            candidate("b", abstract="We randomised 640 students.", authors=("Sari, A.",)),
        ]
    )
    # Shared author alone stays weak: research groups run several distinct studies.
    assert signals[0].tier is LinkTier.WEAK_CANDIDATE
    assert signals[0].signals["shared_sample_sizes"] == []


def test_case_d_unrelated_works_produce_no_signal() -> None:
    assert (
        find_link_signals(
            [
                candidate("a", authors=("Sari, A.",)),
                candidate("b", title="Soil carbon in peatland", authors=("Tanaka, K.",)),
            ]
        )
        == []
    )


def test_agent_output_rules() -> None:
    data = StudyLinkInput(
        project_id=uuid.uuid4(),
        research_question="Does AI tutoring help?",
        left=LinkCandidate(work_id=uuid.uuid4(), title="Main results", abstract="We enrolled 214."),
        right=LinkCandidate(work_id=uuid.uuid4(), title="Abstract", abstract="Interim of 214."),
    )
    with pytest.raises(ValueError, match="relationship type"):
        StudyLinkOutput(
            same_study=True, confidence=0.9, rationale="Same", evidence=["We enrolled 214."]
        )
    with pytest.raises(ValueError, match="quoted evidence"):
        StudyLinkOutput(
            same_study=True,
            relationship_type=StudyWorkRelationship.SECONDARY_REPORT,
            confidence=0.9,
            rationale="Same",
        )
    fabricated = StudyLinkOutput(
        same_study=True,
        relationship_type=StudyWorkRelationship.SECONDARY_REPORT,
        confidence=0.9,
        rationale="Same study",
        evidence=["Registered as NCT99999999"],
    )
    with pytest.raises(LLMInvalidResponseError, match="exact span"):
        validate_link(data, fabricated)

    thin = StudyLinkOutput(
        same_study=True,
        relationship_type=StudyWorkRelationship.SECONDARY_REPORT,
        confidence=0.6,
        rationale="Same authors and topic",
        evidence=["Main results"],
    )
    with pytest.raises(LLMInvalidResponseError, match="requires_human"):
        validate_link(data, thin)

    grounded = StudyLinkOutput(
        same_study=True,
        relationship_type=StudyWorkRelationship.SECONDARY_REPORT,
        confidence=0.85,
        rationale="Both report the same enrolment",
        evidence=["We enrolled 214."],
    )
    validate_link(data, grounded)


async def seed_screened_corpus(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, works: list[dict[str, Any]]
) -> tuple[str, list[uuid.UUID]]:
    """A project whose works already passed title/abstract screening."""
    from ranah_domain.enums import WorkflowRunStatus
    from ranah_domain.models.project import ResearchFramework, ResearchPlan
    from ranah_domain.models.screening import (
        EligibilityCriterion,
        ReviewProtocol,
        ScreeningDecision,
    )
    from ranah_domain.models.workflow import WorkflowRun
    from test_research_slice import FRAMEWORK, PLAN

    project_id = (await api_client.post("/projects", json={"idea": "AI tutoring"})).json()["id"]
    factory = create_session_factory(db_engine)
    work_ids: list[uuid.UUID] = []
    async with session_scope(factory) as session:
        plan = ResearchPlan(
            project_id=uuid.UUID(project_id),
            version=1,
            status="APPROVED",
            content=PLAN,
            provisional_title=PLAN["provisional_title"],
            problem_statement=PLAN["problem_statement"],
            objective=PLAN["research_objective"],
            scope_summary=PLAN["scope"],
            recommended_method=PLAN["recommended_review_method"],
            recommended_framework=PLAN["recommended_framework"],
            rationale=PLAN["rationale"],
        )
        session.add(plan)
        await session.flush()
        framework = ResearchFramework(
            project_id=uuid.UUID(project_id),
            research_plan_id=plan.id,
            version=1,
            framework_type=FRAMEWORK["framework_type"],
            structured_elements=FRAMEWORK,
            rationale="fixture",
        )
        session.add(framework)
        await session.flush()
        values = {**PROTOCOL}
        values.pop("eligibility_criteria")
        protocol = ReviewProtocol(
            project_id=uuid.UUID(project_id),
            research_plan_id=plan.id,
            framework_id=framework.id,
            research_question="Does AI tutoring help?",
            version=1,
            status="APPROVED",
            **values,
        )
        session.add(protocol)
        await session.flush()
        session.add(EligibilityCriterion(protocol_id=protocol.id, **CRITERION))
        round_run = WorkflowRun(
            project_id=uuid.UUID(project_id),
            temporal_workflow_id=f"fixture-{uuid.uuid4()}",
            workflow_type="TitleAbstractScreeningWorkflow",
            stage="COMPLETED",
            status=WorkflowRunStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            details={"protocol_id": str(protocol.id), "protocol_version": 1},
        )
        session.add(round_run)
        await session.flush()
        for spec in works:
            work = WorkRecord(
                project_id=uuid.UUID(project_id),
                title=spec["title"],
                abstract=spec.get("abstract"),
                publication_year=spec.get("year", 2024),
                publication_type=spec.get("publication_type"),
            )
            session.add(work)
            await session.flush()
            work_ids.append(work.id)
            if spec.get("authors"):
                session.add(
                    WorkMetadataObservation(
                        work_id=work.id,
                        provider="openalex",
                        field_name="authors",
                        field_value={"value": spec["authors"]},
                    )
                )
            session.add(
                ScreeningDecision(
                    project_id=uuid.UUID(project_id),
                    work_id=work.id,
                    protocol_id=protocol.id,
                    protocol_version=1,
                    round_id=round_run.id,
                    stage="TITLE_ABSTRACT",
                    decision="INCLUDE",
                    rationale="Fixture inclusion",
                    reviewer_type="AI",
                )
            )
    return project_id, work_ids


@asynccontextmanager
async def study_worker(
    monkeypatch: pytest.MonkeyPatch, respond: Any = None
) -> AsyncIterator[Client]:
    def default(request: StructuredGenerateRequest) -> dict[str, Any]:
        return {
            "same_study": False,
            "relationship_type": None,
            "confidence": 0.4,
            "rationale": "The reports describe different samples",
            "evidence": [],
            "requires_human": False,
        }

    gateway = LLMGateway(
        {"fake": FakeLLMProvider(structured_response_fn=respond or default)},
        ModelRouter({ModelTier.STANDARD: RoutedModel(provider="fake", model="study-fixture")}),
    )
    monkeypatch.setattr(research, "gateway", lambda: gateway)
    queue = f"studies-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue)
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[StudyLinkingWorkflow],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            studies.link_studies,
            studies.calculate_study_progress,
        ],
    ):
        yield temporal


async def run_build(api_client: httpx.AsyncClient, temporal: Client, project_id: str) -> None:
    response = await api_client.post(f"/projects/{project_id}/studies/build")
    assert response.status_code == 202, response.text
    handle = temporal.get_workflow_handle(f"research-{response.json()['operation_id']}")
    assert await handle.result() == "COMPLETED"


async def test_registration_links_reports_without_calling_the_agent(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, work_ids = await seed_screened_corpus(
        api_client,
        db_engine,
        [
            {
                "title": "AI tutoring: main results",
                "abstract": f"Randomised trial {TRIAL} of 214 students.",
                "authors": ["Sari, A.", "Budi, C."],
            },
            {
                "title": "AI tutoring: conference abstract",
                "abstract": f"Interim findings from {TRIAL}.",
                "publication_type": "conference-abstract",
                "authors": ["Sari, A.", "Budi, C."],
            },
        ],
    )

    def refuse(request: StructuredGenerateRequest) -> dict[str, Any]:
        raise AssertionError("A shared registration must not need an LLM call")

    async with study_worker(monkeypatch, refuse) as temporal:
        await run_build(api_client, temporal, project_id)

    rows = (await api_client.get(f"/projects/{project_id}/studies")).json()
    assert len(rows) == 1
    study = rows[0]
    assert study["registration_id"] == TRIAL
    assert {link["relationship_type"] for link in study["works"]} == {
        "PRIMARY_REPORT",
        "SECONDARY_REPORT",
    }

    # Invariant 7: both publications survive linking.
    async with session_scope(create_session_factory(db_engine)) as session:
        works = await session.scalar(
            select(func.count())
            .select_from(WorkRecord)
            .where(WorkRecord.project_id == uuid.UUID(project_id))
        )
        assert works == 2
        decision = await session.scalar(
            select(StudyLinkDecision).where(
                StudyLinkDecision.project_id == uuid.UUID(project_id),
                StudyLinkDecision.decision == "LINK",
            )
        )
        assert decision is not None and decision.decided_by == "SYSTEM"
        assert TRIAL in decision.evidence[0]


async def test_similar_titles_stay_separate_studies(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = await seed_screened_corpus(
        api_client,
        db_engine,
        [
            {
                "title": "AI tutoring in higher education",
                "abstract": "We randomised 214 students in Jakarta.",
                "authors": ["Sari, A.", "Budi, C."],
            },
            {
                "title": "AI tutoring in higher education: a second trial",
                "abstract": "We randomised 640 students in Bandung.",
                "authors": ["Sari, A.", "Budi, C."],
            },
        ],
    )
    async with study_worker(monkeypatch) as temporal:
        await run_build(api_client, temporal, project_id)

    rows = (await api_client.get(f"/projects/{project_id}/studies")).json()
    assert len(rows) == 2, "Similar titles must not be merged into one study"
    async with session_scope(create_session_factory(db_engine)) as session:
        kept = await session.scalar(
            select(StudyLinkDecision).where(
                StudyLinkDecision.project_id == uuid.UUID(project_id),
                StudyLinkDecision.decision == "KEEP_SEPARATE",
            )
        )
        assert kept is not None and kept.decided_by == "AI"


async def test_uncertain_link_escalates_to_human_review(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, work_ids = await seed_screened_corpus(
        api_client,
        db_engine,
        [
            {
                "title": "AI tutoring trial",
                "abstract": "We randomised 214 students.",
                "authors": ["Sari, A.", "Budi, C."],
            },
            {
                "title": "AI tutoring follow-up",
                "abstract": "Follow-up of 214 students.",
                "authors": ["Sari, A.", "Budi, C."],
            },
        ],
    )

    def uncertain(request: StructuredGenerateRequest) -> dict[str, Any]:
        return {
            "same_study": True,
            "relationship_type": "FOLLOW_UP",
            "confidence": 0.55,
            "rationale": "Possibly the same cohort, but recruitment dates are not stated",
            "evidence": ["Follow-up of 214 students."],
            "requires_human": True,
        }

    async with study_worker(monkeypatch, uncertain) as temporal:
        await run_build(api_client, temporal, project_id)

    rows = (await api_client.get(f"/projects/{project_id}/studies")).json()
    assert len(rows) == 2
    assert any(row["status"] == "NEEDS_REVIEW" for row in rows)

    overview = (await api_client.get(f"/projects/{project_id}/studies-overview")).json()
    assert overview["needs_review"] == 1

    # A human resolves it, and the AI's uncertainty stays on the record.
    target = next(row for row in rows if row["status"] != "NEEDS_REVIEW")
    pending = next(row for row in rows if row["status"] == "NEEDS_REVIEW")
    moved = pending["works"][0]["work_id"]
    response = await api_client.post(
        f"/projects/{project_id}/studies/link",
        json={
            "work_id": moved,
            "target_study_id": target["study_id"] if "study_id" in target else target["id"],
            "decision": "LINK",
            "relationship_type": "FOLLOW_UP",
            "rationale": "Authors confirmed the same cohort",
        },
    )
    assert response.status_code == 201, response.text

    after = (await api_client.get(f"/projects/{project_id}/studies")).json()
    assert len(after) == 1 and len(after[0]["works"]) == 2
    async with session_scope(create_session_factory(db_engine)) as session:
        history = list(
            await session.scalars(
                select(StudyLinkDecision).where(
                    StudyLinkDecision.project_id == uuid.UUID(project_id)
                )
            )
        )
        assert {row.decided_by for row in history} == {"AI", "HUMAN"}
        assert {row.decision.value for row in history} == {"UNCERTAIN", "LINK"}


async def test_study_link_decisions_are_immutable(db_engine: AsyncEngine) -> None:
    async with session_scope(create_session_factory(db_engine)) as session:
        row = await session.scalar(select(StudyLinkDecision).limit(1))
        if row is None:
            pytest.skip("No study link decision available in this run")
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                __import__("sqlalchemy").text(
                    "UPDATE study_link_decisions SET rationale = 'changed' WHERE id = :id"
                ),
                {"id": row.id},
            )


async def test_each_included_work_gets_a_study(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, work_ids = await seed_screened_corpus(
        api_client,
        db_engine,
        [{"title": "A single unrelated study", "abstract": "One trial.", "authors": ["Lee, D."]}],
    )
    async with study_worker(monkeypatch) as temporal:
        await run_build(api_client, temporal, project_id)
    rows = (await api_client.get(f"/projects/{project_id}/studies")).json()
    assert len(rows) == 1 and rows[0]["study_label"] == "S01"
    assert rows[0]["works"][0]["relationship_type"] == "PRIMARY_REPORT"
    async with session_scope(create_session_factory(db_engine)) as session:
        links = await session.scalar(
            select(func.count())
            .select_from(StudyWork)
            .join(Study, Study.id == StudyWork.study_id)
            .where(Study.project_id == uuid.UUID(project_id))
        )
        assert links == 1

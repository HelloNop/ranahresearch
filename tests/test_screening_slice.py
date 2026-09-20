import json
import uuid
from typing import Any, cast

import httpx
import pytest
from pydantic import ValidationError
from ranah_agents.screening import ProtocolOutput, ScreeningOutput
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.models import AgentRun, ResearchFramework, ResearchPlan, WorkRecord
from ranah_domain.models.screening import ScreeningDecision
from ranah_domain.schemas.screening import BoundCriterion, Criterion, evaluate
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import StructuredGenerateRequest
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration import screening_activities as activities
from ranah_worker_orchestration.screening_workflows import (
    ProtocolWorkflow,
    TitleAbstractScreeningWorkflow,
)
from ranah_workflow import connect_client
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.worker import Worker
from test_research_slice import FRAMEWORK, PLAN
from test_research_slice import api_client as api_client

CRITERION: dict[str, Any] = {
    "dimension": "POPULATION",
    "operator": "MATCHES",
    "value": {"description": "University students"},
    "decision": "INCLUDE",
    "reason": "Research question population",
    "priority": 0,
}
PROTOCOL: dict[str, Any] = {
    "background": "Map generative AI use in university learning.",
    "objective": "Map learning outcomes.",
    "review_type": "SCOPING_REVIEW",
    "eligibility_criteria": [CRITERION],
    "information_sources": [],
    "screening_strategy": "Recall-oriented title and abstract screening with human review.",
    "extraction_strategy": "Extract learning outcomes after full-text review.",
    "synthesis_strategy": "Map the literature thematically.",
    "risk_of_bias_plan": "Not mandatory for this mapping question.",
    "meta_analysis_plan": "No pooling planned.",
    "meta_analysis_planned": False,
    "assumptions": [],
    "uncertainties": ["Discovery is incomplete."],
}


@pytest.mark.parametrize(
    "dimension,operator,value,metadata,expected",
    [
        ("YEAR", "GTE", 2020, 2024, "PASS"),
        ("YEAR", "GTE", 2020, 2019, "FAIL"),
        ("YEAR", "LTE", 2020, 2024, "FAIL"),
        ("YEAR", "LTE", 2020, 2019, "PASS"),
        ("LANGUAGE", "IN", ["en", "id"], "en", "PASS"),
        ("PUBLICATION_TYPE", "IN", ["journal-article"], "review", "FAIL"),
        ("PUBLICATION_TYPE", "NOT_IN", ["review"], "review", "FAIL"),
        ("PUBLICATION_TYPE", "NOT_IN", ["review"], "journal-article", "PASS"),
        ("YEAR", "GTE", 2020, None, "UNKNOWN"),
        ("LANGUAGE", "IN", ["en"], None, "UNKNOWN"),
    ],
)
def test_deterministic_criteria(
    dimension: str, operator: str, value: Any, metadata: Any, expected: str
) -> None:
    field = {
        "YEAR": "publication_year",
        "LANGUAGE": "language",
        "PUBLICATION_TYPE": "publication_type",
    }[dimension]
    criterion = BoundCriterion.model_validate(
        {
            **CRITERION,
            "id": uuid.uuid4(),
            "dimension": dimension,
            "operator": operator,
            "value": value,
        }
    )
    assert evaluate(criterion, {field: metadata}, {field}).result == expected
    assert evaluate(criterion, {field: metadata}, set()).result == "UNKNOWN"


def test_invalid_criteria_and_screening() -> None:
    for value in (True, "2020", {"arbitrary": "json"}, [2020]):
        with pytest.raises(ValidationError):
            Criterion.model_validate(
                {**CRITERION, "dimension": "YEAR", "operator": "GTE", "value": value}
            )
    with pytest.raises(ValidationError):
        ScreeningOutput.model_validate(
            {
                "decision": "EXCLUDE",
                "reason_code": "FULL_TEXT_UNAVAILABLE",
                "rationale": "not relevant",
                "confidence": 0.9,
                "criterion_assessments": [],
                "evidence_spans": [],
            }
        )
    assert ProtocolOutput.model_validate(PROTOCOL).eligibility_criteria


async def prepare(client: httpx.AsyncClient, engine: AsyncEngine, count: int) -> str:
    project_id = (await client.post("/projects", json={"idea": "University AI learning"})).json()[
        "id"
    ]
    async with session_scope(create_session_factory(engine)) as session:
        plan = ResearchPlan(
            project_id=uuid.UUID(project_id), version=1, status="APPROVED", content=PLAN
        )
        session.add(plan)
        await session.flush()
        session.add(
            ResearchFramework(
                project_id=uuid.UUID(project_id),
                research_plan_id=plan.id,
                framework_type="PCC",
                structured_elements=FRAMEWORK,
            )
        )
        for index in range(count):
            abstract = (
                "University students learned using AI."
                if index % 3 == 0
                else "Primary school children used AI."
                if index % 3 == 1
                else None
            )
            session.add(
                WorkRecord(
                    project_id=uuid.UUID(project_id), title=f"Learning {index}", abstract=abstract
                )
            )
    return str(project_id)


@pytest.mark.parametrize("mode", ["success", "transient", "partial"])
async def test_protocol_screening_end_to_end(
    api_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    attempts = 0
    broken = mode != "success"

    def respond(request: StructuredGenerateRequest) -> dict[str, Any]:
        nonlocal attempts, broken
        if request.schema_name == "ProtocolOutput":
            return PROTOCOL
        attempts += 1
        if broken and attempts > 10:
            if mode == "transient":
                broken = False
                raise RuntimeError("Transient outage")
            raise RuntimeError("Persistent outage")
        data = json.loads(request.messages[1].content)
        abstract = data["abstract"]
        decision = (
            "UNCERTAIN"
            if abstract is None
            else "INCLUDE"
            if "University" in abstract
            else "EXCLUDE"
        )
        return {
            "decision": decision,
            "reason_code": "WRONG_POPULATION" if decision == "EXCLUDE" else None,
            "rationale": "Explicitly wrong population"
            if decision == "EXCLUDE"
            else "Eligible population"
            if decision == "INCLUDE"
            else "Abstract unavailable",
            "confidence": 0.9 if abstract else 0.2,
            "evidence_spans": [abstract] if abstract else [],
            "criterion_assessments": [
                {
                    "criterion_id": c["id"],
                    "result": "FAIL"
                    if decision == "EXCLUDE"
                    else "PASS"
                    if abstract
                    else "UNKNOWN",
                    "reason": "Population assessed from abstract" if abstract else "Not reported",
                    "evidence": abstract,
                }
                for c in data["eligibility_criteria"]
            ],
        }

    fake = FakeLLMProvider(structured_response_fn=respond)
    gateway = LLMGateway(
        {"fake": fake},
        ModelRouter({ModelTier.STANDARD: RoutedModel(provider="fake", model="screening-fixture")}),
    )
    monkeypatch.setattr(research, "gateway", lambda: gateway)
    queue_name = f"screening-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue_name)
    monkeypatch.setenv("SCREENING_BATCH_SIZE", "10")
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue_name,
        workflows=[ProtocolWorkflow, TitleAbstractScreeningWorkflow],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            activities.generate_protocol,
            activities.prepare_screening_batch,
            activities.run_screening_batch,
            activities.calculate_screening_progress,
        ],
    ):
        project_id = await prepare(api_client, db_engine, 100 if mode == "success" else 20)
        base = f"/projects/{project_id}"

        async def command(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
            response = await api_client.post(base + path, json=body or {})
            assert response.status_code == 202, response.text
            operation_id = response.json()["operation_id"]
            await temporal.get_workflow_handle(f"research-{operation_id}").result()
            return cast(
                dict[str, Any], (await api_client.get(base + f"/operations/{operation_id}")).json()
            )

        assert (await api_client.post(base + "/screening/title-abstract/start")).status_code == 409
        assert (await command("/protocol/generate"))["status"] == "COMPLETED"
        protocol = (await api_client.get(base + "/protocol")).json()
        assert protocol["created_by_agent_run_id"] and protocol["version"] == 1
        assert (await api_client.get(base + "/eligibility-criteria")).json()[0][
            "dimension"
        ] == "POPULATION"
        approve_path = base + f"/protocol/{protocol['id']}/approve"
        assert (await api_client.post(approve_path, json={})).status_code == 409
        assert (
            await api_client.post(approve_path, json={"acknowledge_uncertainties": True})
        ).status_code == 200
        assert (
            await api_client.post(approve_path, json={"acknowledge_uncertainties": True})
        ).status_code == 409
        op = await command("/screening/title-abstract/start")
        assert op["status"] == ("PARTIAL" if mode == "partial" else "COMPLETED"), op
        progress = (await api_client.get(base + "/screening/title-abstract/progress")).json()
        if mode == "partial":
            assert progress["screened"] == 10 and progress["remaining"] == 10
            broken = False
            assert (await command("/screening/title-abstract/start"))["status"] == "COMPLETED"
            progress = (await api_client.get(base + "/screening/title-abstract/progress")).json()
        assert progress["screened"] == progress["total"]
        assert (
            progress["include"] + progress["exclude"] + progress["uncertain"] == progress["total"]
        )
        excluded = (await api_client.get(base + "/screening/title-abstract?filter=EXCLUDE")).json()[
            0
        ]
        wid = excluded["work_id"]
        assert (
            await api_client.post(
                base + f"/works/{wid}/screening-decisions",
                json={"round_id": progress["round_id"], "decision": "EXCLUDE"},
            )
        ).status_code == 422
        override = await api_client.post(
            base + f"/works/{wid}/screening-decisions",
            json={"round_id": progress["round_id"], "decision": "INCLUDE"},
        )
        assert override.status_code == 201, override.text
        history = (await api_client.get(base + f"/works/{wid}/screening-history")).json()
        assert (
            len(history) == 2
            and history[0]["reviewer_type"] == "HUMAN"
            and history[1]["decision"] == "EXCLUDE"
        )
        rows = (
            await api_client.get(base + "/screening/title-abstract?filter=HUMAN_OVERRIDDEN")
        ).json()
        assert rows[0]["effective"]["decision"] == "INCLUDE"
        revised = await api_client.post(
            base + f"/protocol/{protocol['id']}/revise",
            json={
                "protocol": {**PROTOCOL, "objective": "Revised mapping scope"},
                "reason": "Clarify scope",
            },
        )
        assert revised.status_code == 201, revised.text
        v2 = revised.json()
        assert v2["version"] == 2
        assert (
            await api_client.post(
                base + f"/protocol/{v2['id']}/approve", json={"acknowledge_uncertainties": True}
            )
        ).status_code == 200
        assert all(
            row["protocol_version"] == 1
            for row in (await api_client.get(base + f"/works/{wid}/screening-history")).json()
        )
        assert (await api_client.get(base + "/protocol/versions")).json()[1][
            "status"
        ] == "SUPERSEDED"
        async with session_scope(create_session_factory(db_engine)) as session:
            decisions = list(
                await session.scalars(
                    select(ScreeningDecision).where(
                        ScreeningDecision.project_id == uuid.UUID(project_id)
                    )
                )
            )
            assert len(decisions) == progress["total"] + 1
            assert all(d.agent_run_id for d in decisions if d.reviewer_type == "AI")
            runs = list(
                await session.scalars(
                    select(AgentRun).where(AgentRun.project_id == uuid.UUID(project_id))
                )
            )
            assert all(run.prompt_version == "v1" for run in runs)
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    await session.execute(
                        text("UPDATE screening_decisions SET decision = 'INCLUDE' WHERE id = :id"),
                        {"id": decisions[0].id},
                    )
        if mode == "success":
            before_attempts = attempts
            assert (await command("/screening/title-abstract/start"))["status"] == "COMPLETED"
            assert attempts == before_attempts + 100


@pytest.mark.parametrize("case", ["include", "population", "missing", "design", "fabricated"])
async def test_screening_agent_scientific_fixtures(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, case: str
) -> None:
    from ranah_agents.context import AgentTask, ContextBuilder
    from ranah_agents.runtime import run_agent
    from ranah_agents.screening import ScreeningInput, screening_registry
    from ranah_agents.tools import ToolRegistry

    project_id = await prepare(api_client, db_engine, 0)
    abstract = {
        "include": "University students learned using AI.",
        "population": "Primary school children used AI.",
        "missing": None,
        "design": "This commentary discusses AI learning.",
        "fabricated": None,
    }[case]
    criterion = BoundCriterion.model_validate(
        {
            **CRITERION,
            "id": uuid.uuid4(),
            "dimension": "STUDY_DESIGN" if case == "design" else "POPULATION",
            "value": {
                "description": "Empirical primary research"
                if case == "design"
                else "University students"
            },
        }
    )
    payload = ScreeningInput(
        work_id=uuid.uuid4(),
        title="AI learning",
        abstract=abstract,
        publication_year=None,
        language=None,
        publication_type=None,
        protocol_id=uuid.uuid4(),
        protocol_version=1,
        research_question="How does AI support learning?",
        eligibility_criteria=[criterion],
        deterministic_assessments=[],
    )
    excluded = case in ("population", "design", "fabricated")
    evidence = "Invented population evidence" if case == "fabricated" else abstract
    response: dict[str, Any] = {
        "decision": "EXCLUDE" if excluded else "UNCERTAIN" if case == "missing" else "INCLUDE",
        "reason_code": "WRONG_STUDY_DESIGN"
        if case == "design"
        else "WRONG_POPULATION"
        if excluded
        else None,
        "rationale": "Criterion assessed from supplied abstract",
        "confidence": 0.8,
        "criterion_assessments": [
            {
                "criterion_id": str(criterion.id),
                "result": "FAIL" if excluded else "UNKNOWN" if case == "missing" else "PASS",
                "reason": "Compare population or design",
                "evidence": evidence,
            }
        ],
        "evidence_spans": [evidence] if evidence else [],
    }
    fake = FakeLLMProvider(structured_response_fn=lambda _: response)
    gateway = LLMGateway(
        {"fake": fake},
        ModelRouter({ModelTier.STANDARD: RoutedModel(provider="fake", model="fixture")}),
    )
    async with session_scope(create_session_factory(db_engine)) as session:
        result = await run_agent(
            session,
            screening_registry(),
            ContextBuilder(ToolRegistry(), gateway),
            name="screening_agent",
            version="1",
            project_id=uuid.UUID(project_id),
            task=AgentTask(task_type="screening_agent", payload=payload.model_dump(mode="json")),
        )
        assert result.agent_run_id
        if case == "fabricated":
            assert result.status == "FAILED" and len(fake.calls) == 3
        else:
            assert result.status == "SUCCESS"
            assert isinstance(result.structured_output, ScreeningOutput)
            assert result.structured_output.decision == response["decision"]
            assert result.structured_output.reason_code == response["reason_code"]


async def test_canonical_screening_corpus(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    from ranah_domain.models.dedupe import DuplicateDecision, DuplicateGroup, DuplicateMember
    from ranah_domain.repositories.screening import canonical_ids

    project_id = uuid.UUID(await prepare(api_client, db_engine, 3))
    async with session_scope(create_session_factory(db_engine)) as session:
        ids = await canonical_ids(session, project_id)
        group = DuplicateGroup(
            project_id=project_id, duplicate_type="EXACT_TITLE", status="RESOLVED"
        )
        session.add(group)
        await session.flush()
        session.add_all(
            [DuplicateMember(duplicate_group_id=group.id, work_id=key) for key in ids[:2]]
        )
        session.add(
            DuplicateDecision(
                duplicate_group_id=group.id, canonical_work_id=ids[0], decision="MERGE"
            )
        )
        await session.flush()
        assert await canonical_ids(session, project_id) == [ids[0], ids[2]]


async def test_prescreening_criterion_amendment(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    from ranah_domain.models.screening import (
        EligibilityCriterion,
        ProtocolAmendment,
        ReviewProtocol,
    )

    pid = uuid.UUID(await prepare(api_client, db_engine, 0))
    async with session_scope(create_session_factory(db_engine)) as session:
        plan = await session.scalar(select(ResearchPlan).where(ResearchPlan.project_id == pid))
        framework = await session.scalar(
            select(ResearchFramework).where(ResearchFramework.project_id == pid)
        )
        assert plan and framework
        protocol = ReviewProtocol(
            project_id=pid,
            research_plan_id=plan.id,
            framework_id=framework.id,
            research_question=PLAN["recommended_research_question"],
            version=1,
            status="PROPOSED",
            **{k: v for k, v in PROTOCOL.items() if k != "eligibility_criteria"},
        )
        session.add(protocol)
        await session.flush()
        protocol_id = protocol.id
        session.add(EligibilityCriterion(protocol_id=protocol.id, **CRITERION))
    year = {**CRITERION, "dimension": "YEAR", "operator": "GTE", "value": 2020, "priority": 1}
    response = await api_client.post(
        f"/projects/{pid}/protocol/{protocol_id}/revise",
        json={
            "protocol": {**PROTOCOL, "eligibility_criteria": [CRITERION, year]},
            "reason": "Set study period before screening",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["version"] == 2
    assert response.json()["eligibility_criteria"][1]["value"] == 2020
    async with session_scope(create_session_factory(db_engine)) as session:
        old_criteria = list(
            await session.scalars(
                select(EligibilityCriterion).where(EligibilityCriterion.protocol_id == protocol_id)
            )
        )
        assert len(old_criteria) == 1 and old_criteria[0].dimension == "POPULATION"
        amendment = await session.scalar(
            select(ProtocolAmendment).where(
                ProtocolAmendment.protocol_id == uuid.UUID(response.json()["id"])
            )
        )
        assert amendment and amendment.change_type == "PRE_SEARCH_CHANGE"
        assert amendment.field_path == "eligibility_criteria"

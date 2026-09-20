import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.fulltext_screening_activities as fts
import ranah_worker_orchestration.parsing_activities as parsing
from pdf_fixtures import ACADEMIC_PAPER, build_pdf
from pydantic import ValidationError
from ranah_agents.screening import RetrievedPassage, ScreeningInput, ScreeningOutput
from ranah_documents.retrieval import select_passages
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.models.screening import ScreeningDecision
from ranah_domain.repositories.screening import final_included_work_ids
from ranah_domain.schemas.screening import Assessment, BoundCriterion, ReasonCode
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import StructuredGenerateRequest
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.fulltext_screening_workflows import FullTextScreeningWorkflow
from ranah_worker_orchestration.parsing_workflows import FullTextParsingWorkflow
from ranah_workflow import connect_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.worker import Worker
from test_research_slice import api_client as api_client
from test_screening_slice import CRITERION
from test_study_linking_slice import seed_screened_corpus

PDF = build_pdf(ACADEMIC_PAPER)


class FakeChunk:
    def __init__(self, index: int, section: str, text: str, page: int = 1) -> None:
        self.chunk_index = index
        self.page_start = page
        self.page_end = page
        self.section_path = section
        self.section_type = section
        self.text = text


def test_retrieval_prefers_relevant_sections_and_demotes_references() -> None:
    chunks = [
        FakeChunk(0, "INTRODUCTION", "Generative AI tools are widely discussed."),
        FakeChunk(1, "METHODS", "We recruited 214 undergraduate students in Indonesia.", page=2),
        FakeChunk(
            2, "REFERENCES", "Undergraduate students and AI tutoring. Journal. 2022.", page=9
        ),
    ]
    passages = select_passages(
        chunks, ["undergraduate students population"], limit=2, prefer_sections=("METHODS",)
    )
    sections = [passage.section_type for passage in passages]
    assert "METHODS" in sections
    assert "REFERENCES" not in sections
    assert next(p for p in passages if p.section_type == "METHODS").page_start == 2


def test_full_text_stage_requires_passages() -> None:
    base: dict[str, Any] = {
        "work_id": uuid.uuid4(),
        "title": "A paper",
        "abstract": None,
        "publication_year": 2024,
        "language": "en",
        "publication_type": "journal-article",
        "protocol_id": uuid.uuid4(),
        "protocol_version": 1,
        "research_question": "Does AI tutoring help?",
        "eligibility_criteria": [],
        "deterministic_assessments": [],
    }
    with pytest.raises(ValueError, match="requires retrieved passages"):
        ScreeningInput(**base, stage="FULL_TEXT")
    with pytest.raises(ValueError, match="must not receive full text"):
        ScreeningInput(
            **base,
            stage="TITLE_ABSTRACT",
            passages=[
                RetrievedPassage(
                    page_start=1, page_end=1, section_path="M", section_type="METHODS", text="x"
                )
            ],
        )


def test_agent_may_not_claim_full_text_is_unavailable() -> None:
    from ranah_agents.screening import validate_screening

    criterion_id = uuid.uuid4()
    criterion = BoundCriterion.model_validate({**CRITERION, "id": criterion_id})
    data = ScreeningInput(
        work_id=uuid.uuid4(),
        title="A paper",
        abstract=None,
        publication_year=2024,
        language="en",
        publication_type="journal-article",
        protocol_id=uuid.uuid4(),
        protocol_version=1,
        research_question="Does AI tutoring help?",
        eligibility_criteria=[criterion],
        deterministic_assessments=[],
        stage="FULL_TEXT",
        passages=[
            RetrievedPassage(
                page_start=2,
                page_end=2,
                section_path="Methods",
                section_type="METHODS",
                text="We recruited 214 undergraduate students.",
            )
        ],
    )
    # The schema alone rejects an unevidenced exclusion.
    with pytest.raises(ValidationError, match="evidenced failed criterion"):
        ScreeningOutput(
            decision="EXCLUDE",
            reason_code=ReasonCode.FULL_TEXT_UNAVAILABLE,
            rationale="I could not read the paper",
            criterion_assessments=[],
            confidence=0.9,
            evidence_spans=[],
        )

    # Even with an evidenced failure, availability is not the agent's to judge.
    claim = ScreeningOutput(
        decision="EXCLUDE",
        reason_code=ReasonCode.FULL_TEXT_UNAVAILABLE,
        rationale="I could not read the paper",
        criterion_assessments=[
            Assessment(
                criterion_id=criterion_id,
                result="FAIL",
                reason="Population contradicted",
                evidence="We recruited 214 undergraduate students.",
            )
        ],
        confidence=0.9,
        evidence_spans=[],
    )
    with pytest.raises(LLMInvalidResponseError, match="retrieval outcome"):
        validate_screening(data, claim)

    # Insufficient data is an allowed, honest full-text answer.
    honest = ScreeningOutput(
        decision="UNCERTAIN",
        reason_code=ReasonCode.INSUFFICIENT_DATA_FOR_ELIGIBILITY,
        rationale="The retrieved passages do not state the comparator",
        criterion_assessments=[
            Assessment(
                criterion_id=criterion_id,
                result="UNKNOWN",
                reason="Not stated in the retrieved passages",
            )
        ],
        confidence=0.3,
        evidence_spans=["We recruited 214 undergraduate students."],
    )
    validate_screening(data, honest)

    with pytest.raises(LLMInvalidResponseError, match="full-text stage"):
        validate_screening(
            ScreeningInput(**{**data.model_dump(), "stage": "TITLE_ABSTRACT", "passages": []}),
            honest,
        )


@asynccontextmanager
async def screening_worker(monkeypatch: pytest.MonkeyPatch, respond: Any) -> AsyncIterator[Client]:
    gateway = LLMGateway(
        {"fake": FakeLLMProvider(structured_response_fn=respond)},
        ModelRouter({ModelTier.STANDARD: RoutedModel(provider="fake", model="fts-fixture")}),
    )
    monkeypatch.setattr(research, "gateway", lambda: gateway)
    queue = f"fts-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue)
    monkeypatch.setenv("SCREENING_BATCH_SIZE", "10")
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[FullTextScreeningWorkflow, FullTextParsingWorkflow],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            fts.prepare_full_text_batch,
            fts.screen_full_text_batch,
            fts.calculate_full_text_progress,
            parsing.prepare_parsing_batch,
            parsing.parse_assets,
            parsing.calculate_parsing_progress,
        ],
    ):
        yield temporal


def responder(request: StructuredGenerateRequest) -> dict[str, Any]:
    """Decides from the retrieved passages, the way the real agent must."""
    data = json.loads(request.messages[1].content)
    passages = " ".join(p["text"] for p in data["passages"])
    criteria = data["eligibility_criteria"]
    if "214 undergraduate students" in passages:
        return {
            "decision": "INCLUDE",
            "reason_code": None,
            "rationale": "Methods on page 2 confirm an undergraduate population",
            "confidence": 0.92,
            "evidence_spans": ["We recruited 214 undergraduate students at two universities"],
            "criterion_assessments": [
                {
                    "criterion_id": c["id"],
                    "result": "PASS",
                    "reason": "Population stated in Methods",
                    "evidence": "We recruited 214 undergraduate students at two universities",
                }
                for c in criteria
            ],
        }
    return {
        "decision": "UNCERTAIN",
        "reason_code": "INSUFFICIENT_DATA_FOR_ELIGIBILITY",
        "rationale": "The retrieved passages do not establish the population",
        "confidence": 0.3,
        "evidence_spans": [],
        "criterion_assessments": [
            {
                "criterion_id": c["id"],
                "result": "UNKNOWN",
                "reason": "Not stated in the retrieved passages",
                "evidence": None,
            }
            for c in criteria
        ],
    }


async def test_full_text_screening_decides_final_inclusion(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, work_ids = await seed_screened_corpus(
        api_client,
        db_engine,
        [
            {"title": "Paper with full text", "abstract": "University students.", "authors": ["A"]},
            {
                "title": "Paper without full text",
                "abstract": "University students.",
                "authors": ["B"],
            },
        ],
    )
    with_text, without_text = work_ids
    base = f"/projects/{project_id}"

    # Invariant 3: a title/abstract INCLUDE is not final inclusion.
    async with session_scope(create_session_factory(db_engine)) as session:
        protocol_id = await session.scalar(
            select(ScreeningDecision.protocol_id).where(
                ScreeningDecision.project_id == uuid.UUID(project_id)
            )
        )
        assert protocol_id is not None
        assert await final_included_work_ids(session, protocol_id) == []

    await api_client.post(
        f"{base}/works/{with_text}/full-text/upload",
        files={"file": ("p.pdf", PDF, "application/pdf")},
    )

    async with screening_worker(monkeypatch, responder) as temporal:
        parse = await api_client.post(f"{base}/works/{with_text}/full-text/parse")
        await temporal.get_workflow_handle(f"research-{parse.json()['operation_id']}").result()

        response = await api_client.post(f"{base}/screening/full-text/start")
        assert response.status_code == 202, response.text
        handle = temporal.get_workflow_handle(f"research-{response.json()['operation_id']}")
        assert await handle.result() == "COMPLETED"

    queue = cast(list[dict[str, Any]], (await api_client.get(f"{base}/screening/full-text")).json())
    by_work = {item["work_id"]: item for item in queue}

    included = by_work[str(with_text)]
    assert included["effective"]["decision"] == "INCLUDE"
    assert included["effective"]["reviewer_type"] == "AI"
    assert "page 2" in included["effective"]["rationale"]
    assert included["full_text_status"] == "AVAILABLE"

    # Invariant 2: no full text means an honest system exclusion, not an AI guess.
    missing = by_work[str(without_text)]
    assert missing["effective"]["decision"] == "EXCLUDE"
    assert missing["effective"]["reason_code"] == "FULL_TEXT_UNAVAILABLE"
    assert missing["effective"]["reviewer_type"] == "SYSTEM"
    assert missing["effective"]["agent_run_id"] is None
    assert missing["full_text_status"] == "NOT_REQUESTED"

    progress = (await api_client.get(f"{base}/screening/full-text/progress")).json()
    assert progress["total"] == 2 and progress["screened"] == 2
    assert progress["unavailable"] == 1 and progress["final_included"] == 1

    async with session_scope(create_session_factory(db_engine)) as session:
        assert await final_included_work_ids(session, protocol_id) == [with_text]
        stages = set(
            await session.scalars(
                select(ScreeningDecision.stage).where(
                    ScreeningDecision.project_id == uuid.UUID(project_id)
                )
            )
        )
        # Both stages coexist; the title/abstract history is not overwritten.
        assert stages == {"TITLE_ABSTRACT", "FULL_TEXT"}


async def test_insufficient_full_text_data_is_uncertain_not_excluded(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, work_ids = await seed_screened_corpus(
        api_client,
        db_engine,
        [{"title": "Thin paper", "abstract": "University students.", "authors": ["C"]}],
    )
    work_id = work_ids[0]
    base = f"/projects/{project_id}"
    thin = build_pdf([["Introduction", "This paper discusses teaching technology broadly."]])
    await api_client.post(
        f"{base}/works/{work_id}/full-text/upload",
        files={"file": ("p.pdf", thin, "application/pdf")},
    )

    async with screening_worker(monkeypatch, responder) as temporal:
        parse = await api_client.post(f"{base}/works/{work_id}/full-text/parse")
        await temporal.get_workflow_handle(f"research-{parse.json()['operation_id']}").result()
        response = await api_client.post(f"{base}/screening/full-text/start")
        handle = temporal.get_workflow_handle(f"research-{response.json()['operation_id']}")
        assert await handle.result() == "COMPLETED"

    queue = (await api_client.get(f"{base}/screening/full-text")).json()
    decision = queue[0]["effective"]
    assert decision["decision"] == "UNCERTAIN"
    assert decision["reason_code"] == "INSUFFICIENT_DATA_FOR_ELIGIBILITY"

    progress = (await api_client.get(f"{base}/screening/full-text/progress")).json()
    assert progress["final_included"] == 0, "Uncertain records are not finally included"

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.extraction_activities as extraction
import ranah_worker_orchestration.fulltext_screening_activities as fts
import ranah_worker_orchestration.parsing_activities as parsing
import ranah_worker_orchestration.risk_activities as risk
import ranah_worker_orchestration.study_activities as studies
import ranah_worker_orchestration.validation_activities as validation
from pdf_fixtures import ACADEMIC_PAPER, build_pdf
from ranah_agents.evidence import (
    ExtractionField,
    ExtractionInput,
    ExtractionOutput,
    ExtractionPassage,
    validate_extraction,
)
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.enums import EvidenceStatus
from ranah_domain.models.evidence import Evidence
from ranah_evidence.schema import default_schema
from ranah_evidence.validation import SEVERITY_ERROR, validate_study_values
from ranah_llm.errors import LLMInvalidResponseError
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import StructuredGenerateRequest
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.extraction_workflows import EvidenceExtractionWorkflow
from ranah_worker_orchestration.fulltext_screening_workflows import FullTextScreeningWorkflow
from ranah_worker_orchestration.parsing_workflows import FullTextParsingWorkflow
from ranah_worker_orchestration.risk_workflows import RiskOfBiasWorkflow
from ranah_worker_orchestration.study_workflows import StudyLinkingWorkflow
from ranah_workflow import connect_client
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.worker import Worker
from test_research_slice import api_client as api_client
from test_study_linking_slice import seed_screened_corpus

PDF = build_pdf(ACADEMIC_PAPER)
SAMPLE_QUOTE = "We recruited 214 undergraduate students at two universities in Indonesia"


def test_extraction_schema_follows_protocol_framework() -> None:
    pico = {field.name for field in default_schema("Does treatment help?", "PICO").fields}
    pcc = {field.name for field in default_schema("What is used?", "PCC").fields}
    assert {"sample_size", "comparator", "effect_estimate"} <= pico
    assert "sample_size" in pcc and "comparator" not in pcc and "effect_estimate" not in pcc


def passage(text: str, page: int = 2, passage_id: int = 1) -> ExtractionPassage:
    return ExtractionPassage(
        passage_id=passage_id,
        work_id=uuid.uuid4(),
        page_start=page,
        page_end=page,
        section_path="Methods > Participants",
        section_type="METHODS",
        text=text,
    )


def extraction_input(fields: list[tuple[str, str]], text: str) -> ExtractionInput:
    return ExtractionInput(
        study_id=uuid.uuid4(),
        study_label="S01",
        research_question="Does AI tutoring help?",
        fields=[
            ExtractionField.model_validate(
                {"name": name, "label": name, "kind": kind, "evidence_type": "QUANTITATIVE"}
            )
            for name, kind in fields
        ],
        passages=[passage(text)],
    )


def output(**fields: Any) -> ExtractionOutput:
    return ExtractionOutput.model_validate(fields)


def test_extraction_must_quote_supplied_text() -> None:
    data = extraction_input([("sample_size", "INTEGER")], SAMPLE_QUOTE + ".")
    fabricated = output(
        extracted_fields=[
            {
                "field_name": "sample_size",
                "value": 214,
                "value_type": "REPORTED",
                "confidence": 0.9,
                "source_locations": [
                    {"passage_id": 1, "page": 2, "quote": "We enrolled 500 participants"}
                ],
            }
        ]
    )
    with pytest.raises(LLMInvalidResponseError, match="quotes text that does not appear"):
        validate_extraction(data, fabricated)

    invented_passage = output(
        extracted_fields=[
            {
                "field_name": "sample_size",
                "value": 214,
                "value_type": "REPORTED",
                "confidence": 0.9,
                "source_locations": [{"passage_id": 99, "page": 2, "quote": SAMPLE_QUOTE}],
            }
        ]
    )
    with pytest.raises(LLMInvalidResponseError, match="not supplied"):
        validate_extraction(data, invented_passage)

    grounded = output(
        extracted_fields=[
            {
                "field_name": "sample_size",
                "value": 214,
                "value_type": "REPORTED",
                "confidence": 0.9,
                "source_locations": [{"passage_id": 1, "page": 2, "quote": SAMPLE_QUOTE}],
            }
        ]
    )
    validate_extraction(data, grounded)


def test_derived_values_must_show_their_derivation() -> None:
    with pytest.raises(ValueError, match="record its derivation"):
        output(
            extracted_fields=[
                {
                    "field_name": "sample_size",
                    "value": 214,
                    "value_type": "DERIVED",
                    "confidence": 0.8,
                    "source_locations": [{"passage_id": 1, "page": 2, "quote": SAMPLE_QUOTE}],
                }
            ]
        )
    derived = output(
        extracted_fields=[
            {
                "field_name": "sample_size",
                "value": 214,
                "value_type": "DERIVED",
                "derivation": "107 intervention + 107 control = 214",
                "confidence": 0.8,
                "source_locations": [{"passage_id": 1, "page": 2, "quote": SAMPLE_QUOTE}],
            }
        ]
    )
    validate_extraction(extraction_input([("sample_size", "INTEGER")], SAMPLE_QUOTE), derived)


def test_every_requested_field_is_accounted_for() -> None:
    data = extraction_input([("sample_size", "INTEGER"), ("comparator", "TEXT")], SAMPLE_QUOTE)
    partial = output(
        extracted_fields=[
            {
                "field_name": "sample_size",
                "value": 214,
                "value_type": "REPORTED",
                "confidence": 0.9,
                "source_locations": [{"passage_id": 1, "page": 2, "quote": SAMPLE_QUOTE}],
            }
        ]
    )
    with pytest.raises(LLMInvalidResponseError, match="every requested field"):
        validate_extraction(data, partial)

    complete = output(
        extracted_fields=partial.extracted_fields,
        missing_fields=[
            {"field_name": "comparator", "reason": "The passages do not describe a comparator"}
        ],
    )
    validate_extraction(data, complete)


def test_numeric_fields_reject_text_values() -> None:
    data = extraction_input([("sample_size", "INTEGER")], SAMPLE_QUOTE)
    textual = output(
        extracted_fields=[
            {
                "field_name": "sample_size",
                "value": "two hundred and fourteen",
                "value_type": "REPORTED",
                "confidence": 0.9,
                "source_locations": [{"passage_id": 1, "page": 2, "quote": SAMPLE_QUOTE}],
            }
        ]
    )
    with pytest.raises(LLMInvalidResponseError, match="plain number"):
        validate_extraction(data, textual)


@pytest.mark.parametrize(
    "values,units,expected_code",
    [
        ({"events": 30, "total": 20}, {}, "EVENTS_EXCEED_TOTAL"),
        ({"intervention_sd": -2.5}, {}, "NEGATIVE_DISPERSION"),
        ({"sample_size": -5}, {}, "NEGATIVE_COUNT"),
        ({"dropout_rate": 140}, {"dropout_rate": "%"}, "PERCENTAGE_OUT_OF_RANGE"),
        ({"sample_size": 214, "intervention_n": 107, "comparator_n": 90}, {}, "ARM_TOTAL_MISMATCH"),
        ({"effect_estimate": "4.2 (95% CI 6.3 to 2.1)"}, {}, "CI_BOUNDS_REVERSED"),
        ({"effect_estimate": "9.9 (95% CI 2.1 to 6.3)"}, {}, "ESTIMATE_OUTSIDE_CI"),
    ],
)
def test_deterministic_numerical_validation(
    values: dict[str, Any], units: dict[str, str | None], expected_code: str
) -> None:
    findings = validate_study_values(values, units)
    assert expected_code in {finding.code for finding in findings}
    assert any(finding.severity == SEVERITY_ERROR for finding in findings)


def test_valid_numbers_raise_no_error() -> None:
    findings = validate_study_values(
        {
            "sample_size": 214,
            "intervention_n": 107,
            "comparator_n": 107,
            "intervention_sd": 6.1,
            "effect_estimate": "4.2 (95% CI 2.1 to 6.3)",
        },
        {},
    )
    assert [f for f in findings if f.severity == SEVERITY_ERROR] == []


def extraction_responder(wrong_sample_size: bool = False) -> Any:
    def respond(request: StructuredGenerateRequest) -> dict[str, Any]:
        data = json.loads(request.messages[1].content)
        if request.schema_name == "EvidenceReviewOutput":
            verdicts = []
            corpus = " ".join(p["text"] for p in data["passages"])
            for item in data["items"]:
                value = str(item["value"])
                found = value in corpus or (
                    item["field_name"] == "sample_size" and "214" in corpus and value == "214"
                )
                verdicts.append(
                    {
                        "evidence_id": item["evidence_id"],
                        "status": "VERIFIED" if found else "CONFLICT",
                        "reason": "The passage states this value"
                        if found
                        else f"The passages do not state {value} for {item['field_name']}",
                        "source_check": [SAMPLE_QUOTE],
                        "corrected_value": None if found else 214,
                        "confidence": 0.9,
                    }
                )
            return {"verdicts": verdicts}

        passages = data["passages"]
        target = next(
            (p for p in passages if "214 undergraduate students" in p["text"]), passages[0]
        )
        quote = SAMPLE_QUOTE if SAMPLE_QUOTE in target["text"] else target["text"][:60]
        extracted = [
            {
                "field_name": "sample_size",
                "value": 500 if wrong_sample_size else 214,
                "unit": "participants",
                "value_type": "REPORTED",
                "confidence": 0.9,
                "source_locations": [
                    {
                        "passage_id": target["passage_id"],
                        "page": target["page_start"],
                        "quote": quote,
                    }
                ],
            }
        ]
        missing = [
            {"field_name": field["name"], "reason": "Not reported in the retrieved passages"}
            for field in data["fields"]
            if field["name"] != "sample_size"
        ]
        return {"extracted_fields": extracted, "missing_fields": missing, "uncertain_fields": []}

    return respond


@asynccontextmanager
async def pipeline_worker(monkeypatch: pytest.MonkeyPatch, respond: Any) -> AsyncIterator[Client]:
    provider = FakeLLMProvider(structured_response_fn=respond)
    gateway = LLMGateway(
        {"fake": provider},
        ModelRouter(
            {
                ModelTier.STANDARD: RoutedModel(provider="fake", model="fixture"),
                ModelTier.HIGH_PRECISION_EXTRACTION: RoutedModel(
                    provider="fake", model="fixture-extraction"
                ),
            }
        ),
    )
    monkeypatch.setattr(research, "gateway", lambda: gateway)
    queue = f"extract-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue)
    monkeypatch.setenv("EXTRACTION_BATCH_SIZE", "2")
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[
            EvidenceExtractionWorkflow,
            FullTextParsingWorkflow,
            FullTextScreeningWorkflow,
            StudyLinkingWorkflow,
            RiskOfBiasWorkflow,
        ],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            parsing.prepare_parsing_batch,
            parsing.parse_assets,
            parsing.calculate_parsing_progress,
            fts.prepare_full_text_batch,
            fts.screen_full_text_batch,
            fts.calculate_full_text_progress,
            studies.link_studies,
            studies.calculate_study_progress,
            extraction.resolve_extraction_corpus,
            extraction.ensure_extraction_schema,
            extraction.prepare_extraction_batch,
            extraction.extract_evidence_batch,
            extraction.calculate_extraction_progress,
            validation.validate_project_evidence,
            validation.review_evidence,
            validation.recheck_evidence,
            risk.assess_risk_of_bias,
        ],
    ):
        yield temporal


def screening_responder(request: StructuredGenerateRequest) -> dict[str, Any]:
    data = json.loads(request.messages[1].content)
    return {
        "decision": "INCLUDE",
        "reason_code": None,
        "rationale": "Methods confirm an eligible population on page 2",
        "confidence": 0.9,
        "evidence_spans": [],
        "criterion_assessments": [
            {
                "criterion_id": c["id"],
                "result": "PASS",
                "reason": "Population stated in Methods",
                "evidence": None,
            }
            for c in data["eligibility_criteria"]
        ],
    }


async def run_pipeline(
    api_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    *,
    wrong_sample_size: bool = False,
    risk_study_type: str | None = None,
    rerun_extraction: bool = False,
) -> tuple[str, Client]:
    """Upload, parse, full-text screen, link studies, then extract."""
    project_id, work_ids = await seed_screened_corpus(
        api_client,
        db_engine,
        [
            {
                "title": "AI tutoring trial",
                "abstract": "University students.",
                "authors": ["Sari, A."],
            }
        ],
    )
    base = f"/projects/{project_id}"
    await api_client.post(
        f"{base}/works/{work_ids[0]}/full-text/upload",
        files={"file": ("p.pdf", PDF, "application/pdf")},
    )

    def combined(request: StructuredGenerateRequest) -> dict[str, Any]:
        if request.schema_name == "ScreeningOutput":
            return screening_responder(request)
        if request.schema_name == "RiskOutput":
            data = json.loads(request.messages[1].content)
            return {
                "domain_assessments": [
                    {
                        "domain_code": code,
                        "judgement": "UNASSESSED",
                        "rationale": "No explicit method in selected passages",
                    }
                    for code in data["domains"]
                ],
                "overall_judgement": "NOT_ASSESSED",
                "requires_human": True,
            }
        return cast(dict[str, Any], extraction_responder(wrong_sample_size)(request))

    worker = pipeline_worker(monkeypatch, combined)
    temporal = await worker.__aenter__()

    async def run(path: str) -> dict[str, Any]:
        response = await api_client.post(base + path)
        assert response.status_code == 202, response.text
        operation = response.json()["operation_id"]
        await temporal.get_workflow_handle(f"research-{operation}").result()
        result = cast(
            dict[str, Any], (await api_client.get(base + f"/operations/{operation}")).json()
        )
        assert result["status"] == "COMPLETED", result
        return result

    await run(f"/works/{work_ids[0]}/full-text/parse")
    await run("/screening/full-text/start")
    await run("/studies/build")
    await run("/extraction/start")
    if rerun_extraction:
        await run("/extraction/start")
    if risk_study_type:
        study_id = (await api_client.get(base + "/studies")).json()[0]["id"]
        classified = await api_client.post(
            base + f"/studies/{study_id}/design",
            json={"study_type": risk_study_type, "reason": "Design confirmed by reviewer"},
        )
        assert classified.status_code == 200, classified.text
        await run("/risk-of-bias/start")
        await run("/risk-of-bias/start")
    return project_id, temporal


async def test_extraction_produces_provenance_linked_evidence(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch)
    base = f"/projects/{project_id}"

    matrix = (await api_client.get(f"{base}/evidence/matrix")).json()
    assert matrix["columns"], "The matrix takes its columns from the extraction schema"
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert row["extraction_status"] == "EXTRACTED"
    sample = row["cells"]["sample_size"]
    assert sample["value"] == 214 and sample["has_provenance"] is True

    items = (await api_client.get(f"{base}/evidence?field_name=sample_size")).json()
    assert len(items) == 1
    item = items[0]
    assert item["value_type"] == "REPORTED"
    provenance = item["provenance"][0]
    # Invariant 5: the number is traceable to a page, a section, and a quote.
    assert provenance["page"] == 2
    assert "Methods" in provenance["section"]
    assert SAMPLE_QUOTE in provenance["evidence_text"]
    assert provenance["chunk_id"] and provenance["parsed_document_id"]
    assert item["verification_status"] == "VERIFIED"

    # Invariant 6: unreported fields are explicitly missing, never invented.
    missing = (await api_client.get(f"{base}/evidence?value_type=MISSING")).json()
    assert missing, "Fields the paper does not report must be recorded as missing"
    assert all(entry["value"] is None for entry in missing)
    assert all(entry["notes"] for entry in missing)

    progress = (await api_client.get(f"{base}/evidence/progress")).json()
    assert progress["included_studies"] == 1 and progress["extraction_complete"] == 1
    assert progress["missing_values"] > 0


async def test_reviewer_detects_a_wrong_extraction(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deliberately wrong value must not pass verification."""
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch, wrong_sample_size=True)
    base = f"/projects/{project_id}"

    items = (await api_client.get(f"{base}/evidence?field_name=sample_size")).json()
    item = items[0]
    assert item["value"] == 500
    assert item["verification_status"] == "CONFLICT"
    verdict = next(v for v in item["verifications"] if v["method"] == "EVIDENCE_REVIEWER_AGENT")
    assert verdict["status"] == "CONFLICT"
    assert verdict["findings"][0]["corrected_value"] == 214

    conflicts = (await api_client.get(f"{base}/evidence-conflicts")).json()
    assert len(conflicts) == 1


async def test_human_correction_preserves_ai_history(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch, wrong_sample_size=True)
    base = f"/projects/{project_id}"
    original = (await api_client.get(f"{base}/evidence?field_name=sample_size")).json()[0]

    response = await api_client.post(
        f"{base}/evidence/{original['id']}/correct",
        json={
            "value": 214,
            "unit": "participants",
            "value_type": "USER_ENTERED",
            "reason": "Methods on page 2 state 107 per arm",
            "evidence_text": SAMPLE_QUOTE,
            "page": 2,
            "section": "Methods > Participants",
        },
    )
    assert response.status_code == 201, response.text
    corrected = response.json()
    assert corrected["value"] == 214 and corrected["value_type"] == "USER_ENTERED"
    assert corrected["entered_by"]

    # Both states remain traceable.
    history_values = {entry["value"] for entry in corrected["history"]}
    assert {214, 500} <= history_values
    assert any(entry["value_type"] == "REPORTED" for entry in corrected["history"])

    current = (await api_client.get(f"{base}/evidence?field_name=sample_size")).json()
    assert len(current) == 1 and current[0]["value"] == 214

    async with session_scope(create_session_factory(db_engine)) as session:
        rows = list(
            await session.scalars(
                select(Evidence).where(
                    Evidence.project_id == uuid.UUID(project_id),
                    Evidence.field_name == "sample_size",
                )
            )
        )
        assert len(rows) == 2
        superseded = next(r for r in rows if r.status == EvidenceStatus.SUPERSEDED)
        assert superseded.value_json == 500 and superseded.superseded_by is not None
        assert superseded.extractor_run_id is not None

    # A correction that breaks a deterministic rule is refused outright.
    replacement_id = corrected["id"]
    bad = await api_client.post(
        f"{base}/evidence/{replacement_id}/correct",
        json={"value": -3, "value_type": "USER_ENTERED", "reason": "typo"},
    )
    assert bad.status_code == 422 and "negative" in bad.text.lower()


async def test_evidence_values_cannot_be_edited_in_place(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch)
    async with session_scope(create_session_factory(db_engine)) as session:
        row = await session.scalar(
            select(Evidence).where(Evidence.project_id == uuid.UUID(project_id)).limit(1)
        )
        assert row is not None
        with pytest.raises(DBAPIError, match="superseding"):
            await session.execute(
                __import__("sqlalchemy").text(
                    "UPDATE evidence SET value_json = '999' WHERE id = :id"
                ),
                {"id": row.id},
            )


async def test_extraction_requires_full_text_inclusion(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    """Invariant 4: a title/abstract INCLUDE alone cannot start extraction."""
    project_id, _ = await seed_screened_corpus(
        api_client,
        db_engine,
        [{"title": "Not yet full-text screened", "abstract": "Students.", "authors": ["D"]}],
    )
    response = await api_client.post(f"/projects/{project_id}/extraction/start")
    assert response.status_code == 409
    assert "full-text screening" in response.text


async def test_extraction_rerun_keeps_one_current_value_per_field(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch, rerun_extraction=True)
    rows = (await api_client.get(f"/projects/{project_id}/evidence?field_name=sample_size")).json()
    assert len(rows) == 1

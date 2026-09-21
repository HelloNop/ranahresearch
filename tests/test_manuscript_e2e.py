"""EPIC-030–039 end-to-end: evidence to an exported, auditable manuscript.

Drives the real Temporal workflow against a fixture project whose evidence was
produced by the actual extraction pipeline, so Methods and Results are checked
against counts the project genuinely persisted rather than against fixtures
written next to the assertion. The LLM is faked throughout: no test reaches a
provider.
"""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx
import pytest
import ranah_worker_orchestration.manuscript_activities as manuscript
from ranah_domain.db import create_session_factory, session_scope
from ranah_domain.enums import (
    EvidenceStatus,
    EvidenceValueType,
    EvidenceVerificationStatus,
    ResearchMethod,
)
from ranah_domain.models.evidence import Evidence
from ranah_domain.models.project import ResearchPlan, ResearchProject, ResearchQuestion
from ranah_llm.gateway import LLMGateway
from ranah_llm.models import StructuredGenerateRequest
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from ranah_worker_orchestration import research_activities as research
from ranah_worker_orchestration.manuscript_workflows import (
    ManuscriptGenerationWorkflow,
    ManuscriptReviewWorkflow,
    ManuscriptRevisionWorkflow,
)
from ranah_workflow import connect_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.worker import Worker
from test_extraction_slice import api_client as api_client
from test_extraction_slice import run_pipeline

CONTRARY_VALUE = "no significant difference between groups"
OVERSTATED_CLAIM = "The intervention dramatically transforms every learner."
GROUNDED_CLAIM = "Several included studies reported improved outcomes."


async def seed_manuscript_ready_project(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Run the real pipeline, then make the project eligible for manuscript generation.

    The pipeline yields one included study with one verified value. A second
    verified value that points the other way is added to the same study so the
    synthesis has genuinely conflicting evidence to keep or flatten.
    """
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch, risk_study_type="RCT")
    factory = create_session_factory(db_engine)
    async with session_scope(factory) as session:
        project = await session.get(ResearchProject, uuid.UUID(project_id))
        assert project is not None
        project.research_method = ResearchMethod.SCOPING_REVIEW
        plan = await session.scalar(
            select(ResearchPlan).where(ResearchPlan.project_id == project.id)
        )
        assert plan is not None
        session.add(
            ResearchQuestion(
                project_id=project.id,
                research_plan_id=plan.id,
                question_type="PRIMARY",
                question_text="Does AI tutoring improve academic performance?",
                is_primary=True,
            )
        )
        existing = await session.scalar(
            select(Evidence).where(
                Evidence.project_id == project.id, Evidence.status == EvidenceStatus.CURRENT
            )
        )
        assert existing is not None
        session.add(
            Evidence(
                project_id=project.id,
                study_id=existing.study_id,
                work_id=existing.work_id,
                extraction_schema_id=existing.extraction_schema_id,
                evidence_type=existing.evidence_type,
                field_name="effect_estimate",
                value_json=CONTRARY_VALUE,
                value_type=EvidenceValueType.REPORTED,
                verification_status=EvidenceVerificationStatus.VERIFIED,
                status=EvidenceStatus.CURRENT,
            )
        )
    return project_id


def manuscript_responder(blocking_forever: bool = False) -> Any:
    """A fake council: one fixable Discussion issue, or one unfixable blocker."""
    rounds = {"review": 0}

    def respond(request: StructuredGenerateRequest) -> dict[str, Any]:
        data = json.loads(request.messages[1].content)
        prompt = request.messages[0].content
        name = request.schema_name

        if name == "SynthesisOutput":
            supporting, contrary = _split_evidence(data["evidence"])
            both = [
                {"evidence_id": supporting, "relationship": "SUPPORTS"},
                {"evidence_id": contrary, "relationship": "CONTRADICTS"},
            ]
            return {
                "themes": [
                    {
                        "label": "Mixed short-term academic performance",
                        "description": "Reported directions differ across the extracted values.",
                        "evidence": both,
                        "confidence": "LOW",
                    }
                ],
                "findings": [
                    {
                        "theme_index": 0,
                        "text": GROUNDED_CLAIM,
                        "evidence": both,
                        "confidence": "LOW",
                    }
                ],
                "contradictions": [
                    {
                        "description": "One extracted outcome improved while another did not.",
                        "interpretation": "The direction of effect is not settled here.",
                        "evidence": both,
                        "confidence": "LOW",
                    }
                ],
                "research_gaps": [
                    {
                        "gap_type": "OUTCOME_GAP",
                        "description": "Long-term outcomes were not reported.",
                        "supporting_observation": "No included study reported follow-up outcomes.",
                        "scope": "Within the reviewed corpus of this project.",
                        "confidence": "LOW",
                    }
                ],
                "limitations": ["A single included study limits transferability."],
                "confidence_notes": ["Risk of bias was not fully assessed."],
            }

        if name == "ClaimBuilderOutput":
            supporting, contrary = _split_evidence(data["evidence"])
            finding_id = data["findings"][0]["id"]
            links = [
                {"evidence_id": supporting, "relationship": "SUPPORTS"},
                {"evidence_id": contrary, "relationship": "CONTRADICTS"},
            ]
            return {
                "claims": [
                    {
                        "source_finding_id": finding_id,
                        "claim_type": "DESCRIPTIVE",
                        "text": GROUNDED_CLAIM,
                        "evidence": links,
                        "confidence": "LOW",
                    },
                    {
                        "source_finding_id": finding_id,
                        "claim_type": "COMPARATIVE",
                        "text": OVERSTATED_CLAIM,
                        "evidence": [links[0]],
                        "confidence": "HIGH",
                    },
                ]
            }

        if name == "ClaimReviewOutput":
            ids = [row["evidence_id"] for row in data["evidence"]]
            if data["claim"]["text"] == OVERSTATED_CLAIM:
                return {
                    "status": "UNSUPPORTED",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": ids[1:],
                    "reason": "One included study cannot support a universal statement.",
                    "recommended_qualification": "Report only what the included study measured.",
                    "confidence": "LOW",
                }
            return {
                "status": "PARTIALLY_SUPPORTED",
                "supporting_evidence_ids": ids[:1],
                "contradicting_evidence_ids": ids[1:],
                "reason": "One extracted value agrees and one does not.",
                "recommended_qualification": "Say 'several included studies', not 'studies show'.",
                "confidence": "LOW",
            }

        if name == "PlannerOutput":
            claim_ids = [row["id"] for row in data["claims"]]
            layout = [
                ("INTRODUCTION", "Introduction", "Frame the reviewed question", []),
                ("METHODS", "Methods", "Describe the workflow actually run", []),
                ("RESULTS", "Results", "Report persisted counts and findings", claim_ids),
                ("DISCUSSION", "Discussion", "Interpret without overstating", claim_ids),
                ("LIMITATIONS", "Limitations", "State corpus limits", []),
                ("CONCLUSION", "Conclusion", "Close on what was observed", []),
                ("ABSTRACT", "Abstract", "Summarise the completed body", []),
                ("REFERENCES", "References", "Hold the resolved bibliography", []),
            ]
            return {
                "proposed_title": "AI tutoring and academic performance: a scoping review",
                "word_budget": 100 * len(layout),
                "sections": [
                    {
                        "section_type": section_type,
                        "heading": heading,
                        "objectives": [objective],
                        "claim_ids": claims,
                        "evidence_requirements": ["Use only verified project evidence"],
                        "citation_requirements": ["Cite canonical works by internal id"],
                        "target_words": 100,
                    }
                    for section_type, heading, objective, claims in layout
                ],
            }

        if name == "WriterOutput":
            return _write(data)

        if name == "ReviewOutput":
            return _review(prompt, data, rounds, blocking_forever)

        if name == "RevisionOutput":
            work_ids = [row["work_id"] for row in data["evidence"] if row["work_id"]]
            claims = [row["id"] for row in data["claims"]]
            citation = f" {{cite:{work_ids[0]}}}" if work_ids else ""
            content = (
                f"{GROUNDED_CLAIM}{citation} The opposite result in the same study is "
                "reported alongside it rather than set aside."
            )
            return {
                "content": content,
                "claim_spans": [
                    {"claim_id": claims[0], "exact_text": GROUNDED_CLAIM} if claims else None
                ][: 1 if claims else 0],
                "cited_work_ids": work_ids[:1],
                "resolution_notes": ["Added the contradicting result to the interpretation."],
            }

        raise AssertionError(f"Unexpected structured request for {name}")

    return respond


def _split_evidence(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """The seeded contrary value, and anything else, as (supporting, contradicting)."""
    contrary = next(
        (row["evidence_id"] for row in rows if row.get("value") == CONTRARY_VALUE), None
    )
    supporting = next((row["evidence_id"] for row in rows if row["evidence_id"] != contrary), None)
    assert contrary and supporting, rows
    return supporting, contrary


def _write(data: dict[str, Any]) -> dict[str, Any]:
    """Prose with no numbers of its own: counts are echoed from deterministic facts."""
    section_type = data["section_type"]
    claims = data["claims"]
    work_ids = [row["work_id"] for row in data["evidence"] if row["work_id"]]
    facts = data["deterministic_facts"]
    if section_type in {"METHODS", "RESULTS"}:
        content = " ".join(f"{fact}." for fact in facts)
        return {
            "content": content,
            "claim_spans": [],
            "cited_work_ids": [],
            "summary": f"{section_type.title()} taken from persisted project artifacts",
        }
    if section_type == "ABSTRACT":
        previous = data.get("previous_section_summary") or "the completed body"
        return {
            "content": f"This review summarises {previous} without adding new results.",
            "claim_spans": [],
            "cited_work_ids": [],
            "summary": "Abstract written after the body",
        }
    if claims:
        citation = f" {{cite:{work_ids[0]}}}" if work_ids else ""
        text = cast(str, claims[0]["text"])
        return {
            "content": f"{text}{citation}",
            "claim_spans": [{"claim_id": claims[0]["id"], "exact_text": text}],
            "cited_work_ids": work_ids[:1],
            "summary": f"{section_type.title()} grounded in verified claims",
        }
    return {
        "content": f"This {section_type.lower()} states only what the reviewed corpus supports.",
        "claim_spans": [],
        "cited_work_ids": [],
        "summary": f"{section_type.title()} written from the reviewed corpus",
    }


def _review(
    prompt: str, data: dict[str, Any], rounds: dict[str, int], blocking_forever: bool
) -> dict[str, Any]:
    """Only the scientific reviewer raises anything; the rest return clean reports."""
    if "argument logic" not in prompt:
        return {"summary": "No issue found in scope.", "issues": []}
    if blocking_forever:
        return {
            "summary": "A blocking concern remains.",
            "issues": [
                {
                    "section_id": None,
                    "severity": "BLOCKING",
                    "category": "unsupported_conclusion",
                    "description": "The manuscript asserts more than the corpus can carry.",
                    "evidence": {"scope": "whole manuscript"},
                    "recommended_action": "An author must resolve this before handoff.",
                }
            ],
        }
    rounds["review"] += 1
    if rounds["review"] > 1:
        return {"summary": "The earlier concern was addressed.", "issues": []}
    discussion = next(
        (row["id"] for row in data["sections"] if row["section_type"] == "DISCUSSION"), None
    )
    return {
        "summary": "The Discussion omits the conflicting result.",
        "issues": [
            {
                "section_id": discussion,
                "severity": "MAJOR",
                "category": "ignored_contradiction",
                "description": "The conflicting extracted outcome is not discussed.",
                "evidence": {"section": "Discussion"},
                "recommended_action": "State the conflicting result alongside the favourable one.",
            }
        ],
    }


@asynccontextmanager
async def manuscript_worker(monkeypatch: pytest.MonkeyPatch, respond: Any) -> AsyncIterator[Client]:
    provider = FakeLLMProvider(structured_response_fn=respond)
    gateway = LLMGateway(
        {"fake": provider},
        ModelRouter(
            {
                ModelTier.STANDARD: RoutedModel(provider="fake", model="fixture"),
                ModelTier.HIGH_PRECISION_EXTRACTION: RoutedModel(
                    provider="fake", model="fixture-manuscript"
                ),
            }
        ),
    )
    monkeypatch.setattr(research, "gateway", lambda: gateway)
    queue = f"manuscript-{uuid.uuid4()}"
    monkeypatch.setenv("RANAH_TASK_QUEUE", queue)
    temporal = await connect_client()
    async with Worker(
        temporal,
        task_queue=queue,
        workflows=[
            ManuscriptGenerationWorkflow,
            ManuscriptRevisionWorkflow,
            ManuscriptReviewWorkflow,
        ],
        activities=[
            research.set_operation_stage,
            research.finish_operation,
            manuscript.validate_manuscript_readiness,
            manuscript.generate_synthesis,
            manuscript.build_and_verify_claims,
            manuscript.create_manuscript_plan,
            manuscript.prepare_manuscript,
            manuscript.write_manuscript_section,
            manuscript.complete_manuscript_version,
            manuscript.run_reviewer_council,
            manuscript.revise_open_issues,
            manuscript.finalize_manuscript_review,
        ],
    ):
        yield temporal


async def _run(
    api_client: httpx.AsyncClient, temporal: Client, base: str, path: str
) -> dict[str, Any]:
    response = await api_client.post(base + path)
    assert response.status_code == 202, response.text
    operation = response.json()["operation_id"]
    await temporal.get_workflow_handle(f"research-{operation}").result()
    result = cast(dict[str, Any], (await api_client.get(base + f"/operations/{operation}")).json())
    assert result["status"] == "COMPLETED", result
    return result


async def test_evidence_reaches_an_exported_manuscript(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = await seed_manuscript_ready_project(api_client, db_engine, monkeypatch)
    base = f"/projects/{project_id}"
    async with manuscript_worker(monkeypatch, manuscript_responder()) as temporal:
        await _run(api_client, temporal, base, "/manuscript/generate")

    # Synthesis keeps the conflict and scopes its gap to the corpus.
    synthesis = (await api_client.get(f"{base}/synthesis")).json()
    assert synthesis["status"] in {"GENERATED", "REVIEWED", "APPROVED"}
    # A scoping review must not be labelled as anything stronger than description.
    assert synthesis["method"] == "DESCRIPTIVE_SYNTHESIS"
    assert len(synthesis["contradictions"]) == 1, "a conflicting result must survive synthesis"
    gap = synthesis["research_gaps"][0]
    assert "reviewed corpus" in gap["scope"].lower()
    assert "no research exists" not in gap["description"].lower()

    # The overstated claim is persisted as rejected and never reaches the prose.
    claims = (await api_client.get(f"{base}/claims")).json()
    by_text = {row["text"]: row for row in claims}
    assert by_text[OVERSTATED_CLAIM]["status"] == "REJECTED"
    assert by_text[OVERSTATED_CLAIM]["verification"] == "UNSUPPORTED"
    assert by_text[GROUNDED_CLAIM]["status"] == "VERIFIED"
    assert by_text[GROUNDED_CLAIM]["recommended_qualification"]

    # Claim -> evidence -> study -> work is inspectable end to end.
    detail = (await api_client.get(f"{base}/claims/{by_text[GROUNDED_CLAIM]['id']}")).json()
    assert {row["relationship"] for row in detail["evidence"]} == {"SUPPORTS", "CONTRADICTS"}
    assert detail["studies"] and detail["works"]

    manuscript_view = (await api_client.get(f"{base}/manuscript")).json()
    assert manuscript_view["status"] == "READY_FOR_AUTHOR_REVIEW"
    sections = {row["section_type"]: row for row in manuscript_view["sections"]}
    assert {"INTRODUCTION", "METHODS", "RESULTS", "DISCUSSION", "ABSTRACT"} <= sections.keys()
    assert all(row["status"] == "COMPLETE" for row in manuscript_view["sections"])
    assert OVERSTATED_CLAIM not in json.dumps(manuscript_view["sections"])

    # Methods and Results carry the project's own counts, not invented ones.
    studies = (await api_client.get(f"{base}/studies")).json()
    assert (
        f"Studies included after full-text screening: {len(studies)}"
        in sections["METHODS"]["content"]
    )
    assert "No meta-analysis performed" in sections["RESULTS"]["content"]
    assert "meta-analysis of" not in sections["RESULTS"]["content"].lower()

    # The MAJOR issue was revised, and version 1 survives the revision.
    versions = (await api_client.get(f"{base}/manuscript/versions")).json()
    assert len(versions) >= 2, "a revision must add a version, not overwrite one"
    assert versions[-1]["version"] == 1 and versions[0]["parent_version_id"] == versions[-1]["id"]
    issues = (await api_client.get(f"{base}/review-issues")).json()
    revised = [row for row in issues if row["category"] == "ignored_contradiction"]
    assert revised and all(row["status"] == "RESOLVED" for row in revised)
    assert all(row["severity"] != "BLOCKING" for row in issues if row["status"] == "OPEN")

    # Every format renders from the one structured manuscript.
    for fmt, magic in (
        ("MARKDOWN", b"# "),
        ("DOCX", b"PK"),
        ("PDF", b"%PDF"),
        ("LATEX", b"\\documentclass"),
    ):
        created = await api_client.post(
            f"{base}/exports", json={"format": fmt, "citation_style": "APA_7"}
        )
        assert created.status_code == 201, created.text
        assert created.json()["size"] > 0
        body = (await api_client.get(f"{base}/exports/{created.json()['id']}/download")).content
        assert body.startswith(magic), fmt
    assert len((await api_client.get(f"{base}/exports")).json()) == 4


async def test_unresolved_blocking_issue_withholds_author_review(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = await seed_manuscript_ready_project(api_client, db_engine, monkeypatch)
    base = f"/projects/{project_id}"
    async with manuscript_worker(
        monkeypatch, manuscript_responder(blocking_forever=True)
    ) as temporal:
        await _run(api_client, temporal, base, "/manuscript/generate")

    manuscript_view = (await api_client.get(f"{base}/manuscript")).json()
    blocking = [
        row
        for row in manuscript_view["issues"]
        if row["severity"] == "BLOCKING" and row["status"] == "OPEN"
    ]
    assert blocking, "the fixture reviewer always raises a blocker"
    assert manuscript_view["status"] == "NEEDS_AUTHOR_REVIEW"
    assert manuscript_view["status"] != "READY_FOR_AUTHOR_REVIEW"


async def test_readiness_gate_refuses_a_project_without_evidence(
    api_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = (await api_client.post("/projects", json={"idea": "Untouched idea"})).json()["id"]
    base = f"/projects/{project_id}"
    readiness = (await api_client.get(f"{base}/manuscript/readiness")).json()
    assert readiness["ready"] is False and readiness["blockers"]

    async with manuscript_worker(monkeypatch, manuscript_responder()) as temporal:
        response = await api_client.post(f"{base}/manuscript/generate")
        assert response.status_code == 202, response.text
        operation = response.json()["operation_id"]
        await temporal.get_workflow_handle(f"research-{operation}").result()
        result = (await api_client.get(f"{base}/operations/{operation}")).json()
    assert result["status"] == "PARTIAL"
    assert (await api_client.get(f"{base}/manuscript")).json() is None

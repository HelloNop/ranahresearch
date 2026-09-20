import uuid

import pytest
from pydantic import ValidationError
from ranah_agents.manuscript import (
    ClaimBuilderInput,
    ClaimBuilderOutput,
    ClaimReviewInput,
    ClaimReviewOutput,
    EvidenceContext,
    PlannerOutput,
    RevisionInput,
    RevisionOutput,
    SynthesisInput,
    SynthesisOutput,
    WriterInput,
    WriterOutput,
    validate_claim_review,
    validate_claims,
    validate_revision,
    validate_synthesis,
    validate_writer,
)
from ranah_documents.manuscript import (
    Citation,
    bibliography_entry,
    docx,
    in_text,
    latex,
    markdown,
    pdf,
)
from ranah_domain.enums import CitationStyle, SectionStatus, SectionType, SynthesisMethod
from ranah_domain.models.manuscript import ManuscriptSection
from ranah_llm.errors import LLMInvalidResponseError


def evidence(study_type: str = "CROSS_SECTIONAL") -> EvidenceContext:
    return EvidenceContext(
        evidence_id=uuid.uuid4(),
        study_id=uuid.uuid4(),
        work_id=uuid.uuid4(),
        study_type=study_type,
        field_name="outcome",
        value="improved",
        verification_status="VERIFIED",
        risk_of_bias="SOME_CONCERNS",
    )


def test_synthesis_preserves_explicit_contradiction() -> None:
    positive, negative = evidence(), evidence()
    data = SynthesisInput(
        method=SynthesisMethod.NARRATIVE_SYNTHESIS,
        research_question="Does the intervention help?",
        extraction_schema={},
        evidence=[positive, negative],
    )
    output = SynthesisOutput.model_validate(
        {
            "themes": [
                {
                    "label": "Mixed outcomes",
                    "description": "Studies reported different directions.",
                    "confidence": "MODERATE",
                    "evidence": [
                        {"evidence_id": str(positive.evidence_id), "relationship": "SUPPORTS"},
                        {"evidence_id": str(negative.evidence_id), "relationship": "CONTRADICTS"},
                    ],
                }
            ],
            "findings": [
                {
                    "theme_index": 0,
                    "text": "The reviewed evidence was inconsistent.",
                    "confidence": "MODERATE",
                    "evidence": [
                        {"evidence_id": str(positive.evidence_id), "relationship": "SUPPORTS"},
                        {"evidence_id": str(negative.evidence_id), "relationship": "CONTRADICTS"},
                    ],
                }
            ],
            "contradictions": [
                {
                    "description": "One study improved while one did not.",
                    "confidence": "MODERATE",
                    "evidence": [
                        {"evidence_id": str(positive.evidence_id), "relationship": "SUPPORTS"},
                        {"evidence_id": str(negative.evidence_id), "relationship": "CONTRADICTS"},
                    ],
                }
            ],
        }
    )
    validate_synthesis(data, output)


def test_gap_language_is_corpus_scoped() -> None:
    with pytest.raises(ValidationError, match="reviewed corpus"):
        SynthesisOutput.model_validate(
            {
                "themes": [
                    {
                        "label": "A",
                        "description": "B",
                        "confidence": "LOW",
                        "evidence": [
                            {"evidence_id": str(uuid.uuid4()), "relationship": "SUPPORTS"}
                        ],
                    }
                ],
                "findings": [
                    {
                        "theme_index": 0,
                        "text": "B",
                        "confidence": "LOW",
                        "evidence": [
                            {"evidence_id": str(uuid.uuid4()), "relationship": "SUPPORTS"}
                        ],
                    }
                ],
                "research_gaps": [
                    {
                        "gap_type": "OUTCOME_GAP",
                        "description": "No research exists.",
                        "supporting_observation": "No row.",
                        "scope": "Everywhere",
                        "confidence": "LOW",
                    }
                ],
            }
        )


def test_observational_evidence_cannot_support_causal_claim() -> None:
    rows = [evidence() for _ in range(3)]
    data = ClaimBuilderInput(
        research_question="Does AI help?", findings=[{"id": str(uuid.uuid4())}], evidence=rows
    )
    output = ClaimBuilderOutput.model_validate(
        {
            "claims": [
                {
                    "claim_type": "CAUSAL",
                    "text": "AI causes improved academic performance.",
                    "confidence": "HIGH",
                    "evidence": [
                        {"evidence_id": str(row.evidence_id), "relationship": "SUPPORTS"}
                        for row in rows
                    ],
                }
            ]
        }
    )
    with pytest.raises(LLMInvalidResponseError, match="Causal language"):
        validate_claims(data, output)


def test_partially_supported_claim_requires_qualification() -> None:
    row = evidence()
    candidate = ClaimBuilderOutput.model_validate(
        {
            "claims": [
                {
                    "claim_type": "ASSOCIATIONAL",
                    "text": "AI was associated with improvement.",
                    "confidence": "MODERATE",
                    "evidence": [{"evidence_id": str(row.evidence_id), "relationship": "SUPPORTS"}],
                }
            ]
        }
    ).claims[0]
    data = ClaimReviewInput(claim=candidate, evidence=[row])
    output = ClaimReviewOutput(
        status="PARTIALLY_SUPPORTED",
        supporting_evidence_ids=[row.evidence_id],
        reason="Evidence was mixed.",
        confidence="LOW",
    )
    with pytest.raises(LLMInvalidResponseError, match="qualification"):
        validate_claim_review(data, output)


def test_planner_budget_and_required_sections_are_structured() -> None:
    common = {
        "objectives": ["Use persisted artifacts"],
        "claim_ids": [],
        "evidence_requirements": [],
        "citation_requirements": [],
        "target_words": 100,
    }
    output = PlannerOutput.model_validate(
        {
            "proposed_title": "Review",
            "word_budget": 400,
            "sections": [
                {**common, "section_type": "INTRODUCTION", "heading": "Introduction"},
                {**common, "section_type": "METHODS", "heading": "Methods"},
                {**common, "section_type": "RESULTS", "heading": "Results"},
                {**common, "section_type": "DISCUSSION", "heading": "Discussion"},
            ],
        }
    )
    assert sum(row.target_words for row in output.sections) == output.word_budget


def test_writer_rejects_invented_work_and_meta_analysis() -> None:
    claim_id, allowed_work, invented_work = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    data = WriterInput(
        section_type=SectionType.RESULTS,
        objective="Report findings.",
        claims=[{"id": str(claim_id), "text": "Several studies reported improvement."}],
        evidence=[evidence()],
        deterministic_facts=["No meta-analysis performed in this workflow."],
        allowed_work_ids=[allowed_work],
    )
    output = WriterOutput(
        content=f"A meta-analysis confirmed the result {{cite:{invented_work}}}.",
        claim_spans=[],
        cited_work_ids=[invented_work],
        summary="Results",
    )
    with pytest.raises(LLMInvalidResponseError, match="work that was not supplied"):
        validate_writer(data, output)


def test_revision_rejects_invented_work() -> None:
    row = evidence()
    data = RevisionInput(
        section={"content": "Old text"},
        issues=[{"id": str(uuid.uuid4())}],
        claims=[],
        evidence=[row],
    )
    invented = uuid.uuid4()
    output = RevisionOutput(
        content=f"Updated {{cite:{invented}}}",
        cited_work_ids=[invented],
        resolution_notes=["Kept scope"],
    )
    with pytest.raises(LLMInvalidResponseError, match="not supplied"):
        validate_revision(data, output)


def test_citation_styles_and_all_export_formats() -> None:
    citation = Citation(
        work_id=uuid.uuid4(),
        title="A study",
        authors=("Amina Rahman", "Budi Santoso"),
        year=2025,
        journal="Journal of Evidence",
        volume="2",
        issue="1",
        pages="1-9",
        doi=None,
        incomplete=(),
    )
    assert in_text(citation, CitationStyle.APA_7, 1) == "(Rahman & Santoso, 2025)"
    assert in_text(citation, CitationStyle.VANCOUVER, 2) == "[2]"
    reference = bibliography_entry(citation, CitationStyle.APA_7, 1)
    section = ManuscriptSection(
        manuscript_version_id=uuid.uuid4(),
        section_type=SectionType.RESULTS,
        heading="Results",
        position=1,
        content="Three studies reported mixed findings.",
        word_count=5,
        status=SectionStatus.COMPLETE,
    )
    rendered = [(section, section.content)]
    assert markdown("Review", rendered, [reference]).startswith(b"# Review")
    assert b"\\documentclass" in latex("Review & evidence", rendered, [reference])
    assert docx("Review", rendered, [reference]).startswith(b"PK")
    assert pdf("Review", rendered, [reference]).startswith(b"%PDF")

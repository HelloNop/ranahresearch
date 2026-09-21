import uuid
from typing import cast

import pytest
from pydantic import ValidationError
from ranah_agents.manuscript import (
    ClaimBuilderInput,
    ClaimBuilderOutput,
    ClaimReviewInput,
    ClaimReviewOutput,
    ClaimSpan,
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
    resolve_sections,
)
from ranah_domain.enums import CitationStyle, SectionStatus, SectionType, SynthesisMethod
from ranah_domain.models.manuscript import ManuscriptSection
from ranah_domain.models.organization import Organization
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_domain.repositories import projects as projects_repo
from ranah_domain.schemas.project import ResearchProjectCreate
from ranah_llm.errors import LLMInvalidResponseError
from sqlalchemy.ext.asyncio import AsyncSession


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


def test_synthesis_rejects_flattened_contradiction() -> None:
    """A "contradiction" citing only agreeing evidence is consensus language in disguise."""
    first, second = evidence(), evidence()
    data = SynthesisInput(
        method=SynthesisMethod.NARRATIVE_SYNTHESIS,
        research_question="Does the intervention help?",
        extraction_schema={},
        evidence=[first, second],
    )
    output = SynthesisOutput.model_validate(
        {
            "themes": [
                {
                    "label": "Consistent benefit",
                    "description": "Studies agreed.",
                    "confidence": "MODERATE",
                    "evidence": [
                        {"evidence_id": str(first.evidence_id), "relationship": "SUPPORTS"}
                    ],
                }
            ],
            "findings": [
                {
                    "theme_index": 0,
                    "text": "Studies consistently show improvement.",
                    "confidence": "MODERATE",
                    "evidence": [
                        {"evidence_id": str(first.evidence_id), "relationship": "SUPPORTS"}
                    ],
                }
            ],
            "contradictions": [
                {
                    "description": "Studies disagreed.",
                    "confidence": "LOW",
                    "evidence": [
                        {"evidence_id": str(first.evidence_id), "relationship": "SUPPORTS"},
                        {"evidence_id": str(second.evidence_id), "relationship": "SUPPORTS"},
                    ],
                }
            ],
        }
    )
    with pytest.raises(LLMInvalidResponseError, match="supporting and opposing"):
        validate_synthesis(data, output)


def test_synthesis_cannot_cite_evidence_outside_its_scope() -> None:
    row = evidence()
    data = SynthesisInput(
        method=SynthesisMethod.THEMATIC_SYNTHESIS,
        research_question="Does the intervention help?",
        extraction_schema={},
        evidence=[row],
    )
    stranger = uuid.uuid4()
    output = SynthesisOutput.model_validate(
        {
            "themes": [
                {
                    "label": "Recalled benefit",
                    "description": "Remembered from training data.",
                    "confidence": "HIGH",
                    "evidence": [{"evidence_id": str(stranger), "relationship": "SUPPORTS"}],
                }
            ],
            "findings": [
                {
                    "theme_index": 0,
                    "text": "A benefit was reported.",
                    "confidence": "HIGH",
                    "evidence": [{"evidence_id": str(row.evidence_id), "relationship": "SUPPORTS"}],
                }
            ],
        }
    )
    with pytest.raises(LLMInvalidResponseError, match="outside its scoped input"):
        validate_synthesis(data, output)


def test_supported_claim_needs_supporting_evidence() -> None:
    row = evidence()
    candidate = ClaimBuilderOutput.model_validate(
        {
            "claims": [
                {
                    "claim_type": "DESCRIPTIVE",
                    "text": "Several included studies reported improved outcomes.",
                    "confidence": "MODERATE",
                    "evidence": [{"evidence_id": str(row.evidence_id), "relationship": "SUPPORTS"}],
                }
            ]
        }
    ).claims[0]
    data = ClaimReviewInput(claim=candidate, evidence=[row])
    with pytest.raises(LLMInvalidResponseError, match="requires supporting evidence"):
        validate_claim_review(
            data,
            ClaimReviewOutput(status="SUPPORTED", reason="It looks right.", confidence="HIGH"),
        )


def test_contradicted_claim_records_the_opposing_evidence() -> None:
    supporting, opposing = evidence(), evidence()
    candidate = ClaimBuilderOutput.model_validate(
        {
            "claims": [
                {
                    "claim_type": "COMPARATIVE",
                    "text": "The intervention outperformed the comparator.",
                    "confidence": "LOW",
                    "evidence": [
                        {"evidence_id": str(supporting.evidence_id), "relationship": "SUPPORTS"},
                        {"evidence_id": str(opposing.evidence_id), "relationship": "CONTRADICTS"},
                    ],
                }
            ]
        }
    ).claims[0]
    data = ClaimReviewInput(claim=candidate, evidence=[supporting, opposing])
    output = ClaimReviewOutput(
        status="CONTRADICTED",
        supporting_evidence_ids=[supporting.evidence_id],
        contradicting_evidence_ids=[opposing.evidence_id],
        reason="One included study reported no difference.",
        recommended_qualification="Report the conflicting result explicitly.",
        confidence="LOW",
    )
    validate_claim_review(data, output)
    assert output.contradicting_evidence_ids == [opposing.evidence_id]


def test_claim_review_cannot_cite_evidence_outside_its_scope() -> None:
    row = evidence()
    candidate = ClaimBuilderOutput.model_validate(
        {
            "claims": [
                {
                    "claim_type": "DESCRIPTIVE",
                    "text": "Outcomes improved in the reviewed corpus.",
                    "confidence": "LOW",
                    "evidence": [{"evidence_id": str(row.evidence_id), "relationship": "SUPPORTS"}],
                }
            ]
        }
    ).claims[0]
    with pytest.raises(LLMInvalidResponseError, match="outside its scoped input"):
        validate_claim_review(
            ClaimReviewInput(claim=candidate, evidence=[row]),
            ClaimReviewOutput(
                status="SUPPORTED",
                supporting_evidence_ids=[uuid.uuid4()],
                reason="Recalled a supporting trial.",
                confidence="HIGH",
            ),
        )


def test_writer_cannot_invent_screening_counts_or_sample_sizes() -> None:
    claim_id = uuid.uuid4()
    data = WriterInput(
        section_type=SectionType.RESULTS,
        objective="Report what the workflow actually produced.",
        claims=[{"id": str(claim_id), "text": "Outcomes improved in the reviewed corpus."}],
        evidence=[evidence()],
        deterministic_facts=[
            "Title and abstract records screened: 12",
            "Studies included after full-text screening: 3",
            "No meta-analysis performed in this workflow.",
        ],
        allowed_work_ids=[],
    )
    invented = WriterOutput(
        content="We screened 4210 records and pooled 812 participants across the included trials.",
        summary="Results",
    )
    with pytest.raises(LLMInvalidResponseError, match="outside supplied facts"):
        validate_writer(data, invented)

    grounded = WriterOutput(
        content="Title and abstract records screened: 12, and 3 studies were finally included.",
        summary="Results",
    )
    validate_writer(data, grounded)


def test_writer_claim_spans_must_quote_the_generated_prose() -> None:
    claim_id = uuid.uuid4()
    data = WriterInput(
        section_type=SectionType.DISCUSSION,
        objective="Interpret the primary findings.",
        claims=[{"id": str(claim_id), "text": "Outcomes improved in the reviewed corpus."}],
        evidence=[evidence()],
        allowed_work_ids=[],
    )
    output = WriterOutput(
        content="The reviewed corpus points in a favourable direction.",
        claim_spans=[ClaimSpan(claim_id=claim_id, exact_text="Outcomes improved")],
        summary="Discussion",
    )
    with pytest.raises(LLMInvalidResponseError, match="quote the generated section exactly"):
        validate_writer(data, output)


async def _seed_work(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    title: str,
    authors: list[str],
    year: int | None,
    journal: str | None = None,
    doi: str | None = None,
) -> WorkRecord:
    work = WorkRecord(
        project_id=project_id,
        title=title,
        publication_year=year,
        journal=journal,
        volume="2" if journal else None,
        issue="1" if journal else None,
        pages="10-22" if journal else None,
        doi=doi,
    )
    session.add(work)
    await session.flush()
    session.add(
        WorkMetadataObservation(
            work_id=work.id,
            provider="crossref",
            field_name="authors",
            field_value={"value": [{"name": name} for name in authors]},
        )
    )
    await session.flush()
    return work


def _section(content: str) -> ManuscriptSection:
    return ManuscriptSection(
        manuscript_version_id=uuid.uuid4(),
        section_type=SectionType.RESULTS,
        heading="Results",
        position=1,
        content=content,
        word_count=len(content.split()),
        status=SectionStatus.COMPLETE,
    )


async def test_citation_resolver_deduplicates_orders_and_reports_missing_metadata(
    db_session: AsyncSession,
) -> None:
    org = Organization(name="Citation Org", slug=f"org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    project = await projects_repo.create_project(
        db_session, ResearchProjectCreate(organization_id=org.id, title="Citation project")
    )
    complete = await _seed_work(
        db_session,
        project.id,
        title="A complete trial report",
        authors=["Amina Rahman", "Budi Santoso"],
        year=2025,
        journal="Journal of Evidence",
        doi="10.1000/complete",
    )
    sparse = await _seed_work(
        db_session,
        project.id,
        title="A sparsely described report",
        authors=["Zulkifli Hasan"],
        year=None,
    )
    sections = [
        _section(
            f"The sparse report is cited twice {{cite:{sparse.id}}} and again "
            f"{{cite:{sparse.id}}}, while the complete one appears once {{cite:{complete.id}}}."
        )
    ]

    rendered, bibliography, warnings = await resolve_sections(
        db_session, sections, CitationStyle.VANCOUVER
    )
    content = rendered[0][1]
    assert len(bibliography) == 2, "a work cited twice must appear once in the bibliography"
    assert content.count("[1]") == 2 and content.count("[2]") == 1
    assert bibliography[0].startswith("1. Zulkifli Hasan"), "Vancouver numbers by first appearance"
    assert "{cite:" not in content

    # Missing metadata is reported, never filled in.
    missing = {row["work_id"]: set(cast(list[str], row["missing"])) for row in warnings}
    assert missing == {str(sparse.id): {"year", "journal", "doi"}}
    assert "doi.org" not in bibliography[0], "a missing DOI is never invented"
    assert bibliography[0].endswith("n.d."), "an undated reference must not render 'n.d..'"

    apa_rendered, apa_bibliography, _ = await resolve_sections(
        db_session, sections, CitationStyle.APA_7
    )
    assert apa_bibliography[0].startswith("Amina Rahman"), "APA orders alphabetically by author"
    apa_content = apa_rendered[0][1]
    assert "(Rahman & Santoso, 2025)" in apa_content
    assert apa_content.count("(Hasan, n.d.)") == 2

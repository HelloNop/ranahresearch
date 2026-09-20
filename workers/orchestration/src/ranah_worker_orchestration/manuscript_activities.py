import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import cast

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.manuscript import (
    ClaimBuilderInput,
    ClaimBuilderOutput,
    ClaimReviewInput,
    ClaimReviewOutput,
    EvidenceContext,
    EvidenceReference,
    PlannerInput,
    PlannerOutput,
    ReviewInput,
    ReviewOutput,
    RevisionInput,
    RevisionOutput,
    SynthesisInput,
    SynthesisOutput,
    WriterInput,
    WriterOutput,
    claim_builder_registry,
    claim_reviewer_registry,
    planner_registry,
    reviewer_registry,
    revision_registry,
    synthesis_registry,
    writer_registry,
)
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult
from ranah_agents.runtime import run_agent
from ranah_agents.tools import ToolRegistry
from ranah_domain.db import session_scope
from ranah_domain.enums import (
    AgentRunStatus,
    ClaimBasis,
    ClaimStatus,
    ClaimVerificationStatus,
    ConfidenceLevel,
    EvidenceRelationship,
    EvidenceStatus,
    ManuscriptStatus,
    ManuscriptVersionStatus,
    ProjectStatus,
    ResearchMethod,
    ReviewerType,
    ReviewIssueStatus,
    ReviewSeverity,
    RevisionTaskStatus,
    SectionStatus,
    SectionType,
    StudyType,
    SynthesisMethod,
    SynthesisStatus,
)
from ranah_domain.models.evidence import Evidence, ExtractionSchema
from ranah_domain.models.manuscript import (
    Claim,
    ClaimEvidenceLink,
    ClaimStudyLink,
    ClaimVerification,
    EvidenceSynthesis,
    Manuscript,
    ManuscriptCitation,
    ManuscriptClaimLocation,
    ManuscriptPlan,
    ManuscriptSection,
    ManuscriptSectionPlan,
    ManuscriptVersion,
    ResearchGap,
    ReviewIssue,
    ReviewReport,
    RevisionTask,
    SectionPlanClaim,
    SynthesisContradiction,
    SynthesisEvidenceLink,
    SynthesisFinding,
    SynthesisTheme,
    TargetJournal,
)
from ranah_domain.models.project import ResearchPlan, ResearchProject, ResearchQuestion
from ranah_domain.models.risk_of_bias import RiskOfBiasAssessment
from ranah_domain.models.search import SearchRun
from ranah_domain.models.study import Study, StudyWork
from ranah_domain.repositories.screening import (
    canonical_ids,
    effective_decisions,
    final_included_work_ids,
    latest_protocol,
)
from ranah_domain.schemas.screening import StrictModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research

REVIEWERS = tuple(ReviewerType)


def _synthesis_method(project: ResearchProject, requested: object | None) -> SynthesisMethod:
    if requested:
        return SynthesisMethod(str(requested))
    if project.research_method == ResearchMethod.SCOPING_REVIEW:
        return SynthesisMethod.DESCRIPTIVE_SYNTHESIS
    if project.research_method == ResearchMethod.NARRATIVE_REVIEW:
        return SynthesisMethod.THEMATIC_SYNTHESIS
    return SynthesisMethod.NARRATIVE_SYNTHESIS


def _writing_order(section: ManuscriptSection) -> tuple[int, int]:
    if section.section_type in {SectionType.ABSTRACT, SectionType.KEYWORDS}:
        return (2, section.position)
    if section.section_type == SectionType.REFERENCES:
        return (3, section.position)
    return (1, section.position)


async def _run(
    session: AsyncSession,
    operation_id: str,
    registry: AgentRegistry,
    name: str,
    payload: StrictModel,
) -> AgentResult:
    op = await research.operation(session, operation_id)
    result = await run_agent(
        session,
        registry,
        ContextBuilder(ToolRegistry(), research.gateway()),
        name=name,
        version="1",
        project_id=op.project_id,
        task=AgentTask(task_type=name, payload=payload.model_dump(mode="json")),
        workflow_id=op.temporal_workflow_id,
    )
    if result.status != AgentRunStatus.SUCCESS or result.structured_output is None:
        raise ApplicationError(f"{name} returned invalid output", non_retryable=True)
    return result


async def _evidence_context(session: AsyncSession, project_id: uuid.UUID) -> list[EvidenceContext]:
    rows = list(
        await session.scalars(
            select(Evidence).where(
                Evidence.project_id == project_id,
                Evidence.status == EvidenceStatus.CURRENT,
            )
        )
    )
    studies = {
        row.id: row
        for row in await session.scalars(select(Study).where(Study.project_id == project_id))
    }
    risks: dict[uuid.UUID, str] = {}
    assessments = list(
        await session.scalars(
            select(RiskOfBiasAssessment)
            .where(RiskOfBiasAssessment.project_id == project_id)
            .order_by(RiskOfBiasAssessment.study_id, RiskOfBiasAssessment.version.desc())
        )
    )
    for assessment in assessments:
        risks.setdefault(assessment.study_id, assessment.overall_judgement)
    return [
        EvidenceContext(
            evidence_id=row.id,
            study_id=row.study_id,
            work_id=row.work_id,
            study_type=studies[row.study_id].study_type,
            field_name=row.field_name,
            value=row.value_json,
            verification_status=row.verification_status,
            risk_of_bias=risks.get(row.study_id),
        )
        for row in rows
        if row.study_id in studies
    ]


@activity.defn
async def validate_manuscript_readiness(operation_id: str) -> dict[str, object]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        project = await session.get(ResearchProject, op.project_id)
        assert project is not None
        question = await session.scalar(
            select(ResearchQuestion)
            .where(ResearchQuestion.project_id == project.id, ResearchQuestion.is_primary.is_(True))
            .order_by(ResearchQuestion.created_at.desc())
            .limit(1)
        )
        protocol = await latest_protocol(session, project.id)
        evidence = await _evidence_context(session, project.id)
        blockers: list[str] = []
        warnings: list[str] = []
        if question is None:
            blockers.append("A primary research question is required")
        if project.research_method and project.research_method != "NARRATIVE_REVIEW":
            if protocol is None or protocol.status != "APPROVED":
                blockers.append("An approved protocol is required")
            else:
                corpus = await canonical_ids(session, project.id)
                title_decisions = await effective_decisions(session, protocol.id)
                title_included = {
                    work_id
                    for work_id, decision in title_decisions.items()
                    if decision.decision == "INCLUDE"
                }
                full_text_decisions = await effective_decisions(
                    session, protocol.id, stage="FULL_TEXT"
                )
                if set(corpus) - set(title_decisions):
                    blockers.append("Title and abstract screening is incomplete")
                if title_included - set(full_text_decisions):
                    blockers.append("Full-text screening is incomplete")
                included = set(await final_included_work_ids(session, protocol.id))
                if not included:
                    blockers.append("The approved workflow has no finally included studies")
                links = list(
                    await session.scalars(select(StudyWork).where(StudyWork.work_id.in_(included)))
                )
                linked_works = {row.work_id for row in links}
                if included - linked_works:
                    blockers.append("Every included work must be linked to a Study")
                linked_studies = {row.study_id for row in links}
                evidence_studies = {row.study_id for row in evidence}
                if linked_studies - evidence_studies:
                    blockers.append("Every included Study needs an extraction attempt")
                schema = await session.scalar(
                    select(ExtractionSchema.id).where(ExtractionSchema.project_id == project.id)
                )
                if schema is None:
                    blockers.append("An extraction schema is required")
                supported_studies = list(
                    await session.scalars(
                        select(Study).where(
                            Study.id.in_(linked_studies),
                            Study.study_type.in_([StudyType.RCT, StudyType.QUASI_EXPERIMENTAL]),
                        )
                    )
                )
                assessed = set(
                    await session.scalars(
                        select(RiskOfBiasAssessment.study_id).where(
                            RiskOfBiasAssessment.study_id.in_([row.id for row in supported_studies])
                        )
                    )
                )
                if {row.id for row in supported_studies} - assessed:
                    warnings.append("Some supported study designs lack a risk-of-bias assessment")
        usable = [
            row
            for row in evidence
            if row.verification_status in {"VERIFIED", "PARTIAL"} and row.value is not None
        ]
        if not usable:
            blockers.append("At least one verified or partially verified evidence item is required")
        if blockers:
            raise ApplicationError("; ".join(blockers), non_retryable=True)
        assert question is not None
        if any(row.verification_status == "CONFLICT" for row in evidence):
            warnings.append("Conflicted evidence will be treated as uncertainty, not support")
        readiness: dict[str, object] = {"ready": True, "warnings": warnings}
        op.details = {
            **op.details,
            "research_question_id": str(question.id),
            "protocol_id": str(protocol.id) if protocol else None,
            "readiness": readiness,
        }
        return readiness


@activity.defn
async def generate_synthesis(operation_id: str) -> str:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        existing = op.details.get("synthesis_id")
        if existing:
            return str(existing)
        if op.details.get("kind") != "synthesis":
            current = await session.scalar(
                select(EvidenceSynthesis)
                .where(
                    EvidenceSynthesis.project_id == op.project_id,
                    EvidenceSynthesis.status.in_(
                        [
                            SynthesisStatus.GENERATED,
                            SynthesisStatus.REVIEWED,
                            SynthesisStatus.APPROVED,
                        ]
                    ),
                )
                .order_by(EvidenceSynthesis.version.desc())
                .limit(1)
            )
            if current:
                op.details = {**op.details, "synthesis_id": str(current.id)}
                return str(current.id)
        question = await session.get(
            ResearchQuestion, uuid.UUID(str(op.details["research_question_id"]))
        )
        assert question is not None
        project = await session.get(ResearchProject, op.project_id)
        assert project is not None
        method = _synthesis_method(project, op.details.get("synthesis_method"))
        protocol = await latest_protocol(session, op.project_id)
        schema = await session.scalar(
            select(ExtractionSchema)
            .where(ExtractionSchema.project_id == op.project_id)
            .order_by(ExtractionSchema.version.desc())
            .limit(1)
        )
        evidence = await _evidence_context(session, op.project_id)
        payload = SynthesisInput(
            method=method,
            research_question=question.question_text,
            protocol={"id": str(protocol.id), "status": protocol.status} if protocol else None,
            extraction_schema=schema.schema_json if schema else {},
            evidence=evidence,
        )
        result = await _run(session, operation_id, synthesis_registry(), "synthesis_agent", payload)
        output = result.structured_output
        assert isinstance(output, SynthesisOutput)
        version = (
            await session.scalar(
                select(func.max(EvidenceSynthesis.version)).where(
                    EvidenceSynthesis.project_id == op.project_id,
                    EvidenceSynthesis.research_question_id == question.id,
                )
            )
            or 0
        ) + 1
        previous = list(
            await session.scalars(
                select(EvidenceSynthesis).where(
                    EvidenceSynthesis.project_id == op.project_id,
                    EvidenceSynthesis.research_question_id == question.id,
                    EvidenceSynthesis.status != SynthesisStatus.SUPERSEDED,
                )
            )
        )
        row = EvidenceSynthesis(
            project_id=op.project_id,
            protocol_id=protocol.id if protocol else None,
            research_question_id=question.id,
            version=version,
            status=SynthesisStatus.GENERATED,
            method=method,
            limitations=output.limitations,
            confidence_notes=output.confidence_notes,
            created_by_agent_run_id=result.agent_run_id,
        )
        session.add(row)
        await session.flush()
        for old in previous:
            old.status = SynthesisStatus.SUPERSEDED
        artifact_links: list[tuple[str, uuid.UUID, list[EvidenceReference]]] = []
        theme_ids: list[uuid.UUID] = []
        for position, theme_item in enumerate(output.themes):
            theme = SynthesisTheme(
                synthesis_id=row.id,
                label=theme_item.label,
                description=theme_item.description,
                confidence=ConfidenceLevel(theme_item.confidence),
                position=position,
            )
            session.add(theme)
            await session.flush()
            theme_ids.append(theme.id)
            artifact_links.append(("THEME", theme.id, theme_item.evidence))
        for position, finding_item in enumerate(output.findings):
            finding = SynthesisFinding(
                synthesis_id=row.id,
                theme_id=theme_ids[finding_item.theme_index],
                text=finding_item.text,
                confidence=ConfidenceLevel(finding_item.confidence),
                position=position,
            )
            session.add(finding)
            await session.flush()
            artifact_links.append(("FINDING", finding.id, finding_item.evidence))
        for contradiction_item in output.contradictions:
            contradiction = SynthesisContradiction(
                synthesis_id=row.id,
                description=contradiction_item.description,
                interpretation=contradiction_item.interpretation,
                confidence=ConfidenceLevel(contradiction_item.confidence),
            )
            session.add(contradiction)
            await session.flush()
            artifact_links.append(("CONTRADICTION", contradiction.id, contradiction_item.evidence))
        for gap_item in output.research_gaps:
            session.add(
                ResearchGap(
                    project_id=op.project_id,
                    synthesis_id=row.id,
                    gap_type=gap_item.gap_type,
                    description=gap_item.description,
                    supporting_observation=gap_item.supporting_observation,
                    scope=gap_item.scope,
                    confidence=ConfidenceLevel(gap_item.confidence),
                )
            )
        for artifact_type, artifact_id, links in artifact_links:
            for link in links:
                session.add(
                    SynthesisEvidenceLink(
                        synthesis_id=row.id,
                        artifact_type=artifact_type,
                        artifact_id=artifact_id,
                        evidence_id=link.evidence_id,
                        relationship=EvidenceRelationship(link.relationship),
                    )
                )
        op.details = {**op.details, "synthesis_id": str(row.id)}
        research.event(session, op.project_id, "SYNTHESIS_GENERATED", synthesis_id=str(row.id))
        return str(row.id)


@activity.defn
async def build_and_verify_claims(operation_id: str) -> list[str]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        if op.details.get("claim_ids"):
            return [str(row) for row in cast(list[object], op.details["claim_ids"])]
        if op.details.get("kind") not in {"claims", "synthesis"}:
            synthesis_id = uuid.UUID(str(op.details["synthesis_id"]))
            current_claims = list(
                await session.scalars(
                    select(Claim.id)
                    .join(SynthesisFinding, Claim.source_finding_id == SynthesisFinding.id)
                    .where(
                        Claim.project_id == op.project_id,
                        Claim.status == ClaimStatus.VERIFIED,
                        SynthesisFinding.synthesis_id == synthesis_id,
                    )
                )
            )
            if current_claims:
                values = [str(row) for row in current_claims]
                op.details = {**op.details, "claim_ids": values}
                return values
        synthesis_id = uuid.UUID(str(op.details["synthesis_id"]))
        question = await session.get(
            ResearchQuestion, uuid.UUID(str(op.details["research_question_id"]))
        )
        findings = list(
            await session.scalars(
                select(SynthesisFinding).where(SynthesisFinding.synthesis_id == synthesis_id)
            )
        )
        evidence = await _evidence_context(session, op.project_id)
        payload = ClaimBuilderInput(
            research_question=question.question_text if question else "",
            findings=[
                {"id": str(row.id), "text": row.text, "confidence": row.confidence}
                for row in findings
            ],
            evidence=evidence,
        )
        result = await _run(
            session, operation_id, claim_builder_registry(), "claim_builder", payload
        )
        output = result.structured_output
        assert isinstance(output, ClaimBuilderOutput)
        by_id = {row.evidence_id: row for row in evidence}
        claim_ids: list[str] = []
        for candidate in output.claims:
            review_result = await _run(
                session,
                operation_id,
                claim_reviewer_registry(),
                "claim_evidence_reviewer",
                ClaimReviewInput(claim=candidate, evidence=evidence),
            )
            review = review_result.structured_output
            assert isinstance(review, ClaimReviewOutput)
            accepted = review.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
            claim = Claim(
                project_id=op.project_id,
                source_finding_id=candidate.source_finding_id,
                claim_type=candidate.claim_type,
                basis=ClaimBasis.EVIDENCE,
                text=candidate.text,
                status=ClaimStatus.VERIFIED if accepted else ClaimStatus.REJECTED,
                confidence=ConfidenceLevel(review.confidence),
                created_by="AGENT",
                created_by_agent_run_id=result.agent_run_id,
            )
            session.add(claim)
            await session.flush()
            for link in candidate.evidence:
                session.add(
                    ClaimEvidenceLink(
                        claim_id=claim.id,
                        evidence_id=link.evidence_id,
                        relationship=EvidenceRelationship(link.relationship),
                        strength=ConfidenceLevel(candidate.confidence),
                    )
                )
                source = by_id.get(link.evidence_id)
                if source:
                    session.add(
                        ClaimStudyLink(
                            claim_id=claim.id,
                            study_id=source.study_id,
                            relationship=EvidenceRelationship(link.relationship),
                        )
                    )
            session.add(
                ClaimVerification(
                    claim_id=claim.id,
                    status=ClaimVerificationStatus(review.status),
                    reason=review.reason,
                    recommended_qualification=review.recommended_qualification,
                    confidence=ConfidenceLevel(review.confidence),
                    agent_run_id=review_result.agent_run_id,
                )
            )
            if accepted:
                claim_ids.append(str(claim.id))
        if not claim_ids:
            raise ApplicationError("No evidence-supported claims were produced", non_retryable=True)
        op.details = {**op.details, "claim_ids": claim_ids}
        research.event(session, op.project_id, "CLAIM_GRAPH_VERIFIED", claim_ids=claim_ids)
        return claim_ids


@activity.defn
async def create_manuscript_plan(operation_id: str) -> str:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        if op.details.get("manuscript_plan_id"):
            return str(op.details["manuscript_plan_id"])
        if op.details.get("kind") == "manuscript":
            current_plan = await session.scalar(
                select(ManuscriptPlan)
                .where(ManuscriptPlan.project_id == op.project_id)
                .order_by(ManuscriptPlan.version.desc())
                .limit(1)
            )
            if current_plan:
                planned_claims = set(
                    await session.scalars(
                        select(SectionPlanClaim.claim_id)
                        .join(
                            ManuscriptSectionPlan,
                            SectionPlanClaim.section_plan_id == ManuscriptSectionPlan.id,
                        )
                        .where(ManuscriptSectionPlan.plan_id == current_plan.id)
                    )
                )
                current_claim_ids = {
                    uuid.UUID(str(row)) for row in cast(list[object], op.details["claim_ids"])
                }
                if planned_claims == current_claim_ids:
                    op.details = {**op.details, "manuscript_plan_id": str(current_plan.id)}
                    return str(current_plan.id)
        project = await session.get(ResearchProject, op.project_id)
        question = await session.get(
            ResearchQuestion, uuid.UUID(str(op.details["research_question_id"]))
        )
        claim_id_values = cast(list[object], op.details["claim_ids"])
        claims = list(
            await session.scalars(
                select(Claim).where(Claim.id.in_([uuid.UUID(str(row)) for row in claim_id_values]))
            )
        )
        research_plan = await session.scalar(
            select(ResearchPlan)
            .where(ResearchPlan.project_id == op.project_id)
            .order_by(ResearchPlan.version.desc())
            .limit(1)
        )
        target_journal = (
            await session.get(TargetJournal, project.target_journal_id)
            if project and project.target_journal_id
            else None
        )
        result = await _run(
            session,
            operation_id,
            planner_registry(),
            "manuscript_planner",
            PlannerInput(
                article_type="REVIEW_ARTICLE",
                research_question=question.question_text if question else "",
                project_artifacts={
                    "project_title": project.title if project else "",
                    "research_method": str(project.research_method) if project else "",
                    "research_plan": research_plan.content if research_plan else {},
                },
                claims=[
                    {"id": str(row.id), "text": row.text, "claim_type": row.claim_type}
                    for row in claims
                ],
                target_journal_constraints=(
                    target_journal.requirements if target_journal else None
                ),
            ),
        )
        output = result.structured_output
        assert isinstance(output, PlannerOutput)
        version = (
            await session.scalar(
                select(func.max(ManuscriptPlan.version)).where(
                    ManuscriptPlan.project_id == op.project_id
                )
            )
            or 0
        ) + 1
        plan = ManuscriptPlan(
            project_id=op.project_id,
            version=version,
            status="GENERATED",
            proposed_title=output.proposed_title,
            article_type="REVIEW_ARTICLE",
            target_journal_id=target_journal.id if target_journal else None,
            word_budget=output.word_budget,
            created_by_agent_run_id=result.agent_run_id,
        )
        session.add(plan)
        await session.flush()
        allowed_claim_ids = {row.id for row in claims}
        for position, item in enumerate(output.sections):
            section = ManuscriptSectionPlan(
                plan_id=plan.id,
                section_type=item.section_type,
                heading=item.heading,
                position=position,
                objectives=item.objectives,
                evidence_requirements=item.evidence_requirements,
                citation_requirements=item.citation_requirements,
                target_words=item.target_words,
            )
            session.add(section)
            await session.flush()
            for claim_id in item.claim_ids:
                if claim_id in allowed_claim_ids:
                    session.add(SectionPlanClaim(section_plan_id=section.id, claim_id=claim_id))
        op.details = {**op.details, "manuscript_plan_id": str(plan.id)}
        return str(plan.id)


@activity.defn
async def prepare_manuscript(operation_id: str) -> list[str]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        if op.details.get("manuscript_version_id"):
            sections = list(
                await session.scalars(
                    select(ManuscriptSection)
                    .where(
                        ManuscriptSection.manuscript_version_id
                        == uuid.UUID(str(op.details["manuscript_version_id"]))
                    )
                    .order_by(ManuscriptSection.position)
                )
            )
            return [str(row.id) for row in sorted(sections, key=_writing_order)]
        plan = await session.get(ManuscriptPlan, uuid.UUID(str(op.details["manuscript_plan_id"])))
        assert plan is not None
        manuscript = Manuscript(
            project_id=op.project_id,
            plan_id=plan.id,
            title=plan.proposed_title,
            status=ManuscriptStatus.DRAFT,
            article_type=plan.article_type,
        )
        session.add(manuscript)
        await session.flush()
        version = ManuscriptVersion(
            manuscript_id=manuscript.id,
            version=1,
            status=ManuscriptVersionStatus.DRAFT,
            change_reason="Initial evidence-grounded draft",
            created_by="AGENT",
        )
        session.add(version)
        await session.flush()
        manuscript.current_version_id = version.id
        plans = list(
            await session.scalars(
                select(ManuscriptSectionPlan)
                .where(ManuscriptSectionPlan.plan_id == plan.id)
                .order_by(ManuscriptSectionPlan.position)
            )
        )
        section_ids: list[str] = []
        for item in plans:
            section = ManuscriptSection(
                manuscript_version_id=version.id,
                section_plan_id=item.id,
                section_type=item.section_type,
                heading=item.heading,
                position=item.position,
                status=SectionStatus.PLANNED,
            )
            session.add(section)
            await session.flush()
            section_ids.append(str(section.id))
        op.details = {
            **op.details,
            "manuscript_id": str(manuscript.id),
            "manuscript_version_id": str(version.id),
        }
        created = list(
            await session.scalars(
                select(ManuscriptSection).where(
                    ManuscriptSection.id.in_([uuid.UUID(row) for row in section_ids])
                )
            )
        )
        return [str(row.id) for row in sorted(created, key=_writing_order)]


async def _section_context(
    session: AsyncSession, section: ManuscriptSection
) -> tuple[list[Claim], list[EvidenceContext], list[uuid.UUID]]:
    claim_ids = list(
        await session.scalars(
            select(SectionPlanClaim.claim_id).where(
                SectionPlanClaim.section_plan_id == section.section_plan_id
            )
        )
    )
    claims = list(await session.scalars(select(Claim).where(Claim.id.in_(claim_ids))))
    links = list(
        await session.scalars(
            select(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id.in_(claim_ids))
        )
    )
    evidence_ids = {row.evidence_id for row in links}
    version = await session.get(ManuscriptVersion, section.manuscript_version_id)
    manuscript = await session.get(Manuscript, version.manuscript_id) if version else None
    all_context = await _evidence_context(session, manuscript.project_id) if manuscript else []
    context = [row for row in all_context if row.evidence_id in evidence_ids]
    work_ids = list(dict.fromkeys(row.work_id for row in context if row.work_id))
    return claims, context, work_ids


async def _deterministic_facts(session: AsyncSession, project_id: uuid.UUID) -> list[str]:
    protocol = await latest_protocol(session, project_id)
    evidence_count = await session.scalar(
        select(func.count())
        .select_from(Evidence)
        .where(Evidence.project_id == project_id, Evidence.status == EvidenceStatus.CURRENT)
    )
    runs = list(await session.scalars(select(SearchRun).where(SearchRun.project_id == project_id)))
    facts = [
        f"Persisted current evidence items: {evidence_count or 0}",
        f"Persisted search runs: {len(runs)}",
        f"Persisted records retrieved across search runs: "
        f"{sum(row.result_count_retrieved for row in runs)}",
        "No meta-analysis performed in this workflow.",
    ]
    if protocol:
        title_decisions = await effective_decisions(session, protocol.id)
        full_text_decisions = await effective_decisions(session, protocol.id, stage="FULL_TEXT")
        included = await final_included_work_ids(session, protocol.id)
        facts.extend(
            (
                f"Approved protocol version: {protocol.version}",
                f"Protocol review type: {protocol.review_type}",
                f"Information sources: {', '.join(protocol.information_sources)}",
                f"Title and abstract records screened: {len(title_decisions)}",
                f"Full-text records screened: {len(full_text_decisions)}",
                f"Studies included after full-text screening: {len(included)}",
                f"Screening strategy: {protocol.screening_strategy}",
                f"Extraction strategy: {protocol.extraction_strategy}",
                f"Risk-of-bias process: {protocol.risk_of_bias_plan}",
            )
        )
    return facts


@activity.defn
async def write_manuscript_section(operation_id: str, section_id: str) -> str:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        section = await session.get(ManuscriptSection, uuid.UUID(section_id), with_for_update=True)
        if section is None:
            raise ApplicationError("Manuscript section not found", non_retryable=True)
        if section.status == SectionStatus.COMPLETE:
            return section_id
        version = await session.get(ManuscriptVersion, section.manuscript_version_id)
        manuscript = await session.get(Manuscript, version.manuscript_id) if version else None
        plan = await session.get(ManuscriptSectionPlan, section.section_plan_id)
        assert manuscript is not None and plan is not None
        if section.section_type == SectionType.TITLE:
            section.content = manuscript.title
            section.summary = manuscript.title
            section.status = SectionStatus.COMPLETE
            section.word_count = len(manuscript.title.split())
            return section_id
        if section.section_type == SectionType.REFERENCES:
            section.content = (
                "References are generated deterministically from cited canonical works."
            )
            section.summary = "Deterministic bibliography"
            section.status = SectionStatus.COMPLETE
            section.word_count = len(section.content.split())
            return section_id
        claims, evidence, work_ids = await _section_context(session, section)
        previous = await session.scalar(
            select(ManuscriptSection)
            .where(
                ManuscriptSection.manuscript_version_id == section.manuscript_version_id,
                ManuscriptSection.position < section.position,
                ManuscriptSection.status == SectionStatus.COMPLETE,
            )
            .order_by(ManuscriptSection.position.desc())
            .limit(1)
        )
        facts = await _deterministic_facts(session, op.project_id)
        result = await _run(
            session,
            operation_id,
            writer_registry(),
            "manuscript_writer",
            WriterInput(
                section_type=section.section_type,
                objective="; ".join(plan.objectives),
                claims=[
                    {"id": str(row.id), "text": row.text, "claim_type": row.claim_type}
                    for row in claims
                ],
                evidence=evidence,
                deterministic_facts=facts,
                allowed_work_ids=work_ids,
                previous_section_summary=previous.summary if previous else None,
            ),
        )
        output = result.structured_output
        assert isinstance(output, WriterOutput)
        section.content = output.content
        section.summary = output.summary
        section.word_count = len(output.content.split())
        section.status = SectionStatus.COMPLETE
        section.created_by_agent_run_id = result.agent_run_id
        claim_by_id = {row.id: row for row in claims}
        for span in output.claim_spans:
            start = output.content.index(span.exact_text)
            if span.claim_id in claim_by_id:
                session.add(
                    ManuscriptClaimLocation(
                        section_id=section.id,
                        claim_id=span.claim_id,
                        start_offset=start,
                        end_offset=start + len(span.exact_text),
                        exact_text=span.exact_text,
                    )
                )
        for work_id in output.cited_work_ids:
            token = f"{{cite:{work_id}}}"
            for match in re.finditer(re.escape(token), output.content):
                session.add(
                    ManuscriptCitation(
                        section_id=section.id,
                        work_id=work_id,
                        token=token,
                        start_offset=match.start(),
                        end_offset=match.end(),
                    )
                )
        return section_id


@activity.defn
async def complete_manuscript_version(operation_id: str) -> str:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        version = await session.get(
            ManuscriptVersion,
            uuid.UUID(str(op.details["manuscript_version_id"])),
            with_for_update=True,
        )
        manuscript = await session.get(Manuscript, uuid.UUID(str(op.details["manuscript_id"])))
        assert version is not None and manuscript is not None
        incomplete = await session.scalar(
            select(func.count())
            .select_from(ManuscriptSection)
            .where(
                ManuscriptSection.manuscript_version_id == version.id,
                ManuscriptSection.status != SectionStatus.COMPLETE,
            )
        )
        if incomplete:
            raise ApplicationError("Manuscript has incomplete sections", non_retryable=True)
        version.status = ManuscriptVersionStatus.COMPLETE
        manuscript.status = ManuscriptStatus.IN_REVIEW
        project = await session.get(ResearchProject, op.project_id)
        if project:
            project.status = ProjectStatus.REVIEW
        return str(version.id)


@activity.defn
async def run_reviewer_council(operation_id: str) -> list[str]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        manuscript = await session.get(Manuscript, uuid.UUID(str(op.details["manuscript_id"])))
        version = await session.get(
            ManuscriptVersion, uuid.UUID(str(op.details["manuscript_version_id"]))
        )
        assert manuscript is not None and version is not None
        project = await session.get(ResearchProject, op.project_id)
        target_journal = (
            await session.get(TargetJournal, project.target_journal_id)
            if project and project.target_journal_id
            else None
        )
        sections = list(
            await session.scalars(
                select(ManuscriptSection)
                .where(ManuscriptSection.manuscript_version_id == version.id)
                .order_by(ManuscriptSection.position)
            )
        )
        section_ids = {row.id for row in sections}
        locations = list(
            await session.scalars(
                select(ManuscriptClaimLocation).where(
                    ManuscriptClaimLocation.section_id.in_(section_ids)
                )
            )
        )
        citations = list(
            await session.scalars(
                select(ManuscriptCitation).where(ManuscriptCitation.section_id.in_(section_ids))
            )
        )
        claim_ids = {row.claim_id for row in locations}
        claims = list(await session.scalars(select(Claim).where(Claim.id.in_(claim_ids))))
        evidence_links = list(
            await session.scalars(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id.in_(claim_ids))
            )
        )
        evidence_ids = {row.evidence_id for row in evidence_links}
        evidence_rows = list(
            await session.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids)))
        )
        payload = ReviewInput(
            manuscript_version_id=version.id,
            sections=[
                {
                    "id": str(row.id),
                    "section_type": row.section_type,
                    "heading": row.heading,
                    "content": row.content,
                }
                for row in sections
            ],
            artifacts={
                "manuscript_title": manuscript.title,
                "target_journal": (
                    {"name": target_journal.name, "requirements": target_journal.requirements}
                    if target_journal
                    else None
                ),
                "deterministic_facts": await _deterministic_facts(session, op.project_id),
                "claims": [
                    {
                        "id": str(row.id),
                        "text": row.text,
                        "type": row.claim_type,
                        "status": row.status,
                    }
                    for row in claims
                ],
                "claim_locations": [
                    {
                        "section_id": str(row.section_id),
                        "claim_id": str(row.claim_id),
                        "exact_text": row.exact_text,
                    }
                    for row in locations
                ],
                "claim_evidence_links": [
                    {
                        "claim_id": str(row.claim_id),
                        "evidence_id": str(row.evidence_id),
                        "relationship": row.relationship,
                    }
                    for row in evidence_links
                ],
                "evidence": [
                    {
                        "id": str(row.id),
                        "study_id": str(row.study_id),
                        "work_id": str(row.work_id) if row.work_id else None,
                        "field_name": row.field_name,
                        "value": row.value_json,
                        "verification_status": row.verification_status,
                    }
                    for row in evidence_rows
                ],
                "citations": [
                    {
                        "section_id": str(row.section_id),
                        "work_id": str(row.work_id),
                        "token": row.token,
                    }
                    for row in citations
                ],
            },
        )
        issue_ids: list[str] = []
        for reviewer in REVIEWERS:
            result = await _run(
                session,
                operation_id,
                reviewer_registry(reviewer),
                f"{reviewer.value.lower()}_reviewer",
                payload,
            )
            output = result.structured_output
            assert isinstance(output, ReviewOutput)
            report = ReviewReport(
                project_id=op.project_id,
                manuscript_version_id=version.id,
                reviewer_type=reviewer,
                summary=output.summary,
                agent_run_id=result.agent_run_id,
            )
            session.add(report)
            for item in output.issues:
                issue = ReviewIssue(
                    project_id=op.project_id,
                    manuscript_id=manuscript.id,
                    manuscript_version_id=version.id,
                    section_id=item.section_id if item.section_id in section_ids else None,
                    reviewer_type=reviewer,
                    severity=item.severity,
                    category=item.category,
                    description=item.description,
                    evidence=item.evidence,
                    recommended_action=item.recommended_action,
                )
                session.add(issue)
                await session.flush()
                session.add(
                    RevisionTask(
                        review_issue_id=issue.id,
                        manuscript_id=manuscript.id,
                        section_id=issue.section_id,
                        action_type=("REVISE_SECTION" if issue.section_id else "AUTHOR_REVIEW"),
                        instruction=issue.recommended_action,
                        status=RevisionTaskStatus.OPEN,
                    )
                )
                issue_ids.append(str(issue.id))
        return issue_ids


@activity.defn
async def revise_open_issues(operation_id: str, revision_round: int) -> int:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        manuscript = await session.get(Manuscript, uuid.UUID(str(op.details["manuscript_id"])))
        assert manuscript is not None and manuscript.current_version_id is not None
        current = await session.get(ManuscriptVersion, manuscript.current_version_id)
        assert current is not None
        issue_query = select(ReviewIssue).where(
            ReviewIssue.manuscript_id == manuscript.id,
            ReviewIssue.manuscript_version_id == current.id,
            ReviewIssue.status == ReviewIssueStatus.OPEN,
            ReviewIssue.section_id.is_not(None),
        )
        requested_issue = op.details.get("issue_id")
        if requested_issue:
            issue_query = issue_query.where(ReviewIssue.id == uuid.UUID(str(requested_issue)))
        else:
            issue_query = issue_query.where(
                ReviewIssue.severity.in_([ReviewSeverity.BLOCKING, ReviewSeverity.MAJOR])
            )
        issues = list(await session.scalars(issue_query))
        if not issues:
            return 0
        grouped: dict[uuid.UUID, list[ReviewIssue]] = defaultdict(list)
        for issue in issues:
            if issue.section_id:
                grouped[issue.section_id].append(issue)
        old_sections = list(
            await session.scalars(
                select(ManuscriptSection)
                .where(ManuscriptSection.manuscript_version_id == current.id)
                .order_by(ManuscriptSection.position)
            )
        )
        new_version = ManuscriptVersion(
            manuscript_id=manuscript.id,
            version=current.version + 1,
            status=ManuscriptVersionStatus.DRAFT,
            parent_version_id=current.id,
            change_reason=f"Automatic review revision round {revision_round}",
            created_by="AGENT",
        )
        session.add(new_version)
        await session.flush()
        by_old: dict[uuid.UUID, ManuscriptSection] = {}
        for old in old_sections:
            clone = ManuscriptSection(
                manuscript_version_id=new_version.id,
                section_plan_id=old.section_plan_id,
                section_type=old.section_type,
                heading=old.heading,
                position=old.position,
                content=old.content,
                word_count=old.word_count,
                status=SectionStatus.COMPLETE,
                summary=old.summary,
            )
            session.add(clone)
            await session.flush()
            by_old[old.id] = clone
            if old.id not in grouped:
                old_claims = list(
                    await session.scalars(
                        select(ManuscriptClaimLocation).where(
                            ManuscriptClaimLocation.section_id == old.id
                        )
                    )
                )
                old_citations = list(
                    await session.scalars(
                        select(ManuscriptCitation).where(ManuscriptCitation.section_id == old.id)
                    )
                )
                for location in old_claims:
                    session.add(
                        ManuscriptClaimLocation(
                            section_id=clone.id,
                            claim_id=location.claim_id,
                            start_offset=location.start_offset,
                            end_offset=location.end_offset,
                            exact_text=location.exact_text,
                        )
                    )
                for citation in old_citations:
                    session.add(
                        ManuscriptCitation(
                            section_id=clone.id,
                            work_id=citation.work_id,
                            token=citation.token,
                            start_offset=citation.start_offset,
                            end_offset=citation.end_offset,
                        )
                    )
        for old_id, section_issues in grouped.items():
            section = by_old[old_id]
            claims, evidence, work_ids = await _section_context(session, section)
            result = await _run(
                session,
                operation_id,
                revision_registry(),
                "revision_agent",
                RevisionInput(
                    section={
                        "id": str(section.id),
                        "heading": section.heading,
                        "content": section.content,
                    },
                    issues=[
                        {
                            "id": str(row.id),
                            "description": row.description,
                            "recommended_action": row.recommended_action,
                        }
                        for row in section_issues
                    ],
                    claims=[{"id": str(row.id), "text": row.text} for row in claims],
                    evidence=evidence,
                    deterministic_facts=await _deterministic_facts(session, op.project_id),
                ),
            )
            output = result.structured_output
            assert isinstance(output, RevisionOutput)
            section.content = output.content
            section.word_count = len(output.content.split())
            section.created_by_agent_run_id = result.agent_run_id
            claim_ids = {row.id for row in claims}
            for span in output.claim_spans:
                if span.claim_id not in claim_ids or span.exact_text not in output.content:
                    raise ApplicationError(
                        "Revision introduced an invalid claim mapping", non_retryable=True
                    )
                start = output.content.index(span.exact_text)
                session.add(
                    ManuscriptClaimLocation(
                        section_id=section.id,
                        claim_id=span.claim_id,
                        start_offset=start,
                        end_offset=start + len(span.exact_text),
                        exact_text=span.exact_text,
                    )
                )
            if not set(output.cited_work_ids) <= set(work_ids):
                raise ApplicationError(
                    "Revision cited a work outside its evidence context", non_retryable=True
                )
            for work_id in output.cited_work_ids:
                token = f"{{cite:{work_id}}}"
                for match in re.finditer(re.escape(token), output.content):
                    session.add(
                        ManuscriptCitation(
                            section_id=section.id,
                            work_id=work_id,
                            token=token,
                            start_offset=match.start(),
                            end_offset=match.end(),
                        )
                    )
            for issue in section_issues:
                issue.status = ReviewIssueStatus.RESOLVED
                issue.resolved_at = datetime.now(UTC)
                issue.resolution_reason = "; ".join(output.resolution_notes)
                task = await session.scalar(
                    select(RevisionTask).where(RevisionTask.review_issue_id == issue.id).limit(1)
                )
                if task:
                    task.section_id = section.id
                    task.status = RevisionTaskStatus.COMPLETED
                    task.revision_round = revision_round
                    task.completed_at = datetime.now(UTC)
        new_version.status = ManuscriptVersionStatus.COMPLETE
        manuscript.current_version_id = new_version.id
        op.details = {**op.details, "manuscript_version_id": str(new_version.id)}
        return len(issues)


@activity.defn
async def finalize_manuscript_review(operation_id: str) -> str:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        manuscript = await session.get(Manuscript, uuid.UUID(str(op.details["manuscript_id"])))
        assert manuscript is not None and manuscript.current_version_id is not None
        blockers = await session.scalar(
            select(func.count())
            .select_from(ReviewIssue)
            .where(
                ReviewIssue.manuscript_id == manuscript.id,
                ReviewIssue.manuscript_version_id == manuscript.current_version_id,
                ReviewIssue.status == ReviewIssueStatus.OPEN,
                ReviewIssue.severity.in_([ReviewSeverity.BLOCKING, ReviewSeverity.MAJOR]),
            )
        )
        manuscript.status = (
            ManuscriptStatus.NEEDS_AUTHOR_REVIEW
            if blockers
            else ManuscriptStatus.READY_FOR_AUTHOR_REVIEW
        )
        project = await session.get(ResearchProject, op.project_id)
        if project:
            project.status = ProjectStatus.AUTHOR_REVIEW
        return manuscript.status

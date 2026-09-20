import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Response
from pydantic import Field
from ranah_documents.manuscript import docx, latex, markdown, pdf, resolve_sections
from ranah_domain.enums import (
    CitationStyle,
    EvidenceStatus,
    EvidenceVerificationStatus,
    ExportFormat,
    ExportStatus,
    ManuscriptStatus,
    ManuscriptVersionStatus,
    ReviewIssueStatus,
    ReviewSeverity,
    SectionStatus,
    SynthesisMethod,
    SynthesisStatus,
)
from ranah_domain.models.evidence import Evidence
from ranah_domain.models.manuscript import (
    Claim,
    ClaimEvidenceLink,
    ClaimStudyLink,
    ClaimVerification,
    EvidenceSynthesis,
    Manuscript,
    ManuscriptCitation,
    ManuscriptClaimLocation,
    ManuscriptExport,
    ManuscriptSection,
    ManuscriptVersion,
    ResearchGap,
    ReviewIssue,
    SynthesisContradiction,
    SynthesisEvidenceLink,
    SynthesisFinding,
    SynthesisTheme,
)
from ranah_domain.models.project import ResearchQuestion
from ranah_domain.models.study import Study
from ranah_domain.models.work import WorkRecord
from ranah_domain.schemas.screening import StrictModel, Text
from ranah_domain.storage import object_storage
from sqlalchemy import func, select

from ranah_api.projects import DB, Principal, append_event, error, scoped_project, start_operation

router = APIRouter(prefix="/projects", tags=["Manuscript"])


class SynthesisApproval(StrictModel):
    synthesis_id: uuid.UUID


class SynthesisRequest(StrictModel):
    method: SynthesisMethod | None = None


class SectionEdit(StrictModel):
    content: Text
    reason: Text = Field(default="Manual author edit")


class IssueDecision(StrictModel):
    reason: Text


class ExportRequest(StrictModel):
    format: ExportFormat
    citation_style: CitationStyle = CitationStyle.APA_7


async def _latest_manuscript(session: DB, project_id: uuid.UUID) -> Manuscript | None:
    return cast(
        Manuscript | None,
        await session.scalar(
            select(Manuscript)
            .where(Manuscript.project_id == project_id)
            .order_by(Manuscript.created_at.desc())
            .limit(1)
        ),
    )


@router.get("/{project_id}/manuscript/readiness")
async def readiness(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id)
    question = await session.scalar(
        select(ResearchQuestion.id).where(
            ResearchQuestion.project_id == project_id, ResearchQuestion.is_primary.is_(True)
        )
    )
    usable = await session.scalar(
        select(func.count())
        .select_from(Evidence)
        .where(
            Evidence.project_id == project_id,
            Evidence.status == EvidenceStatus.CURRENT,
            Evidence.verification_status.in_(
                [EvidenceVerificationStatus.VERIFIED, EvidenceVerificationStatus.PARTIAL]
            ),
        )
    )
    blockers = []
    if not question:
        blockers.append("A primary research question is required")
    if not usable:
        blockers.append("Validated evidence is required")
    return {"ready": not blockers, "blockers": blockers, "research_method": project.research_method}


@router.post("/{project_id}/manuscript/generate", status_code=202)
async def generate_manuscript(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    return await start_operation(session, project, "manuscript", {})


@router.post("/{project_id}/synthesis/generate", status_code=202)
async def generate_synthesis_only(
    project_id: uuid.UUID, payload: SynthesisRequest, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    details = {"synthesis_method": payload.method} if payload.method else {}
    return await start_operation(session, project, "synthesis", details)


@router.post("/{project_id}/claims/generate", status_code=202)
async def generate_claims_only(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    return await start_operation(session, project, "claims", {})


@router.post("/{project_id}/manuscript/plan/generate", status_code=202)
async def generate_manuscript_plan_only(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    return await start_operation(session, project, "manuscript_plan", {})


@router.get("/{project_id}/synthesis")
async def get_synthesis(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    row = await session.scalar(
        select(EvidenceSynthesis)
        .where(
            EvidenceSynthesis.project_id == project_id,
            EvidenceSynthesis.status != SynthesisStatus.SUPERSEDED,
        )
        .order_by(EvidenceSynthesis.version.desc())
        .limit(1)
    )
    if row is None:
        return None
    themes = list(
        await session.scalars(
            select(SynthesisTheme)
            .where(SynthesisTheme.synthesis_id == row.id)
            .order_by(SynthesisTheme.position)
        )
    )
    findings = list(
        await session.scalars(
            select(SynthesisFinding)
            .where(SynthesisFinding.synthesis_id == row.id)
            .order_by(SynthesisFinding.position)
        )
    )
    contradictions = list(
        await session.scalars(
            select(SynthesisContradiction).where(SynthesisContradiction.synthesis_id == row.id)
        )
    )
    gaps = list(
        await session.scalars(select(ResearchGap).where(ResearchGap.synthesis_id == row.id))
    )
    links = list(
        await session.scalars(
            select(SynthesisEvidenceLink).where(SynthesisEvidenceLink.synthesis_id == row.id)
        )
    )
    by_artifact: dict[str, list[dict[str, str]]] = {}
    for link in links:
        by_artifact.setdefault(str(link.artifact_id), []).append(
            {"evidence_id": str(link.evidence_id), "relationship": link.relationship}
        )
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "method": row.method,
        "limitations": row.limitations,
        "confidence_notes": row.confidence_notes,
        "themes": [
            {
                "id": item.id,
                "label": item.label,
                "description": item.description,
                "confidence": item.confidence,
                "evidence": by_artifact.get(str(item.id), []),
            }
            for item in themes
        ],
        "findings": [
            {
                "id": item.id,
                "theme_id": item.theme_id,
                "text": item.text,
                "confidence": item.confidence,
                "evidence": by_artifact.get(str(item.id), []),
            }
            for item in findings
        ],
        "contradictions": [
            {
                "id": item.id,
                "description": item.description,
                "interpretation": item.interpretation,
                "confidence": item.confidence,
                "evidence": by_artifact.get(str(item.id), []),
            }
            for item in contradictions
        ],
        "research_gaps": [
            {
                "id": item.id,
                "gap_type": item.gap_type,
                "description": item.description,
                "supporting_observation": item.supporting_observation,
                "scope": item.scope,
                "confidence": item.confidence,
            }
            for item in gaps
        ],
    }


@router.post("/{project_id}/synthesis/approve")
async def approve_synthesis(
    project_id: uuid.UUID, data: SynthesisApproval, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    row = await session.get(EvidenceSynthesis, data.synthesis_id)
    if row is None or row.project_id != project_id or row.status == SynthesisStatus.SUPERSEDED:
        raise error(404, "NOT_FOUND", "Current synthesis not found")
    row.status = SynthesisStatus.APPROVED
    append_event(session, project, user, "SYNTHESIS_APPROVED", synthesis_id=str(row.id))
    return {"id": row.id, "status": row.status}


@router.get("/{project_id}/claims")
async def list_claims(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    rows = list(
        await session.scalars(
            select(Claim).where(Claim.project_id == project_id).order_by(Claim.created_at)
        )
    )
    result = []
    for row in rows:
        verification = await session.scalar(
            select(ClaimVerification)
            .where(ClaimVerification.claim_id == row.id)
            .order_by(ClaimVerification.created_at.desc())
            .limit(1)
        )
        links = list(
            await session.scalars(
                select(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id == row.id)
            )
        )
        result.append(
            {
                "id": row.id,
                "claim_type": row.claim_type,
                "basis": row.basis,
                "text": row.text,
                "status": row.status,
                "confidence": row.confidence,
                "verification": verification.status if verification else None,
                "recommended_qualification": (
                    verification.recommended_qualification if verification else None
                ),
                "evidence": [
                    {"evidence_id": link.evidence_id, "relationship": link.relationship}
                    for link in links
                ],
            }
        )
    return result


@router.get("/{project_id}/claims/{claim_id}")
async def claim_detail(
    project_id: uuid.UUID, claim_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    await scoped_project(session, user, project_id)
    claim = await session.get(Claim, claim_id)
    if claim is None or claim.project_id != project_id:
        raise error(404, "NOT_FOUND", "Claim not found")
    evidence_links = list(
        await session.scalars(
            select(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id == claim.id)
        )
    )
    study_links = list(
        await session.scalars(select(ClaimStudyLink).where(ClaimStudyLink.claim_id == claim.id))
    )
    evidence_rows = {
        row.id: row
        for row in await session.scalars(
            select(Evidence).where(Evidence.id.in_([link.evidence_id for link in evidence_links]))
        )
    }
    studies = {
        row.id: row
        for row in await session.scalars(
            select(Study).where(Study.id.in_([link.study_id for link in study_links]))
        )
    }
    work_ids = {row.work_id for row in evidence_rows.values() if row.work_id}
    works = {
        row.id: row
        for row in await session.scalars(select(WorkRecord).where(WorkRecord.id.in_(work_ids)))
    }
    return {
        "id": claim.id,
        "text": claim.text,
        "claim_type": claim.claim_type,
        "status": claim.status,
        "confidence": claim.confidence,
        "evidence": [
            {
                "id": evidence_rows[link.evidence_id].id,
                "field_name": evidence_rows[link.evidence_id].field_name,
                "value": evidence_rows[link.evidence_id].value_json,
                "relationship": link.relationship,
                "work_id": evidence_rows[link.evidence_id].work_id,
            }
            for link in evidence_links
            if link.evidence_id in evidence_rows
        ],
        "studies": [
            {"id": studies[link.study_id].id, "title": studies[link.study_id].title}
            for link in study_links
            if link.study_id in studies
        ],
        "works": [{"id": row.id, "title": row.title, "doi": row.doi} for row in works.values()],
    }


async def _manuscript_view(session: DB, manuscript: Manuscript) -> dict[str, Any]:
    if manuscript.current_version_id is None:
        return {"id": manuscript.id, "status": manuscript.status, "sections": []}
    version = await session.get(ManuscriptVersion, manuscript.current_version_id)
    sections = list(
        await session.scalars(
            select(ManuscriptSection)
            .where(ManuscriptSection.manuscript_version_id == manuscript.current_version_id)
            .order_by(ManuscriptSection.position)
        )
    )
    issues = list(
        await session.scalars(
            select(ReviewIssue)
            .where(ReviewIssue.manuscript_id == manuscript.id)
            .order_by(ReviewIssue.created_at.desc())
        )
    )
    return {
        "id": manuscript.id,
        "title": manuscript.title,
        "status": manuscript.status,
        "article_type": manuscript.article_type,
        "citation_style": manuscript.citation_style,
        "version": version.version if version else None,
        "version_id": manuscript.current_version_id,
        "sections": [
            {
                "id": row.id,
                "section_type": row.section_type,
                "heading": row.heading,
                "content": row.content,
                "word_count": row.word_count,
                "status": row.status,
            }
            for row in sections
        ],
        "issues": [
            {
                "id": row.id,
                "section_id": row.section_id,
                "reviewer_type": row.reviewer_type,
                "severity": row.severity,
                "category": row.category,
                "description": row.description,
                "recommended_action": row.recommended_action,
                "status": row.status,
            }
            for row in issues
        ],
    }


@router.get("/{project_id}/manuscript")
async def get_manuscript(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    manuscript = await _latest_manuscript(session, project_id)
    return await _manuscript_view(session, manuscript) if manuscript else None


@router.get("/{project_id}/manuscript/versions")
async def manuscript_versions(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    manuscript = await _latest_manuscript(session, project_id)
    if manuscript is None:
        return []
    rows = list(
        await session.scalars(
            select(ManuscriptVersion)
            .where(ManuscriptVersion.manuscript_id == manuscript.id)
            .order_by(ManuscriptVersion.version.desc())
        )
    )
    return [
        {
            "id": row.id,
            "version": row.version,
            "status": row.status,
            "parent_version_id": row.parent_version_id,
            "change_reason": row.change_reason,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/{project_id}/manuscript/sections/{section_id}/edit")
async def edit_section(
    project_id: uuid.UUID,
    section_id: uuid.UUID,
    data: SectionEdit,
    session: DB,
    user: Principal,
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    manuscript = await _latest_manuscript(session, project_id)
    if manuscript is None or manuscript.current_version_id is None:
        raise error(404, "NOT_FOUND", "Manuscript not found")
    source = await session.get(ManuscriptSection, section_id)
    if source is None or source.manuscript_version_id != manuscript.current_version_id:
        raise error(404, "NOT_FOUND", "Current manuscript section not found")
    current = await session.get(ManuscriptVersion, manuscript.current_version_id)
    assert current is not None
    rows = list(
        await session.scalars(
            select(ManuscriptSection)
            .where(ManuscriptSection.manuscript_version_id == current.id)
            .order_by(ManuscriptSection.position)
        )
    )
    version = ManuscriptVersion(
        manuscript_id=manuscript.id,
        version=current.version + 1,
        status=ManuscriptVersionStatus.COMPLETE,
        parent_version_id=current.id,
        change_reason=data.reason,
        created_by="USER",
        created_by_user_id=user.id,
    )
    session.add(version)
    await session.flush()
    edited: ManuscriptSection | None = None
    for row in rows:
        clone = ManuscriptSection(
            manuscript_version_id=version.id,
            section_plan_id=row.section_plan_id,
            section_type=row.section_type,
            heading=row.heading,
            position=row.position,
            content=data.content if row.id == source.id else row.content,
            word_count=len(data.content.split()) if row.id == source.id else row.word_count,
            status=SectionStatus.NEEDS_REVIEW if row.id == source.id else SectionStatus.COMPLETE,
            summary=row.summary,
        )
        session.add(clone)
        await session.flush()
        if row.id == source.id:
            edited = clone
        else:
            locations = list(
                await session.scalars(
                    select(ManuscriptClaimLocation).where(
                        ManuscriptClaimLocation.section_id == row.id
                    )
                )
            )
            citations = list(
                await session.scalars(
                    select(ManuscriptCitation).where(ManuscriptCitation.section_id == row.id)
                )
            )
            for location in locations:
                session.add(
                    ManuscriptClaimLocation(
                        section_id=clone.id,
                        claim_id=location.claim_id,
                        start_offset=location.start_offset,
                        end_offset=location.end_offset,
                        exact_text=location.exact_text,
                    )
                )
            for citation in citations:
                session.add(
                    ManuscriptCitation(
                        section_id=clone.id,
                        work_id=citation.work_id,
                        token=citation.token,
                        start_offset=citation.start_offset,
                        end_offset=citation.end_offset,
                    )
                )
    manuscript.current_version_id = version.id
    manuscript.status = ManuscriptStatus.REVISION_REQUIRED
    append_event(
        session,
        project,
        user,
        "MANUSCRIPT_SECTION_EDITED",
        old_section_id=str(source.id),
        new_section_id=str(edited.id if edited else ""),
        version=version.version,
    )
    return {"version": version.version, "section_id": edited.id if edited else None}


@router.get("/{project_id}/review-issues")
async def review_issues(
    project_id: uuid.UUID,
    session: DB,
    user: Principal,
    status: ReviewIssueStatus | None = None,
    severity: ReviewSeverity | None = None,
) -> Any:
    await scoped_project(session, user, project_id)
    statement = select(ReviewIssue).where(ReviewIssue.project_id == project_id)
    if status:
        statement = statement.where(ReviewIssue.status == status)
    if severity:
        statement = statement.where(ReviewIssue.severity == severity)
    rows = list(await session.scalars(statement.order_by(ReviewIssue.created_at.desc())))
    return [
        {
            "id": row.id,
            "manuscript_id": row.manuscript_id,
            "section_id": row.section_id,
            "reviewer_type": row.reviewer_type,
            "severity": row.severity,
            "category": row.category,
            "description": row.description,
            "recommended_action": row.recommended_action,
            "status": row.status,
        }
        for row in rows
    ]


@router.post("/{project_id}/review-issues/{issue_id}/dismiss")
async def dismiss_issue(
    project_id: uuid.UUID,
    issue_id: uuid.UUID,
    data: IssueDecision,
    session: DB,
    user: Principal,
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    issue = await session.get(ReviewIssue, issue_id)
    if issue is None or issue.project_id != project_id:
        raise error(404, "NOT_FOUND", "Review issue not found")
    issue.status = ReviewIssueStatus.DISMISSED
    issue.resolution_reason = data.reason
    issue.resolved_at = datetime.now(UTC)
    append_event(session, project, user, "REVIEW_ISSUE_DISMISSED", issue_id=str(issue.id))
    return {"id": issue.id, "status": issue.status}


@router.post("/{project_id}/review-issues/{issue_id}/revise", status_code=202)
async def revise_issue(
    project_id: uuid.UUID, issue_id: uuid.UUID, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    issue = await session.get(ReviewIssue, issue_id)
    manuscript = await session.get(Manuscript, issue.manuscript_id) if issue else None
    if issue is None or issue.project_id != project_id or manuscript is None:
        raise error(404, "NOT_FOUND", "Review issue not found")
    return await start_operation(
        session,
        project,
        "revision",
        {
            "manuscript_id": str(manuscript.id),
            "manuscript_version_id": str(manuscript.current_version_id),
            "issue_id": str(issue.id),
        },
    )


@router.post("/{project_id}/manuscript/re-review", status_code=202)
async def rereview(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    manuscript = await _latest_manuscript(session, project_id)
    if manuscript is None or manuscript.current_version_id is None:
        raise error(404, "NOT_FOUND", "Manuscript not found")
    return await start_operation(
        session,
        project,
        "review",
        {
            "manuscript_id": str(manuscript.id),
            "manuscript_version_id": str(manuscript.current_version_id),
        },
    )


@router.post("/{project_id}/exports", status_code=201)
async def create_export(
    project_id: uuid.UUID, data: ExportRequest, session: DB, user: Principal
) -> Any:
    await scoped_project(session, user, project_id, write=True)
    manuscript = await _latest_manuscript(session, project_id)
    if manuscript is None or manuscript.current_version_id is None:
        raise error(409, "WORKFLOW_CONFLICT", "Generate a manuscript first")
    sections = list(
        await session.scalars(
            select(ManuscriptSection)
            .where(ManuscriptSection.manuscript_version_id == manuscript.current_version_id)
            .order_by(ManuscriptSection.position)
        )
    )
    resolved, references, warnings = await resolve_sections(session, sections, data.citation_style)
    renderer = {
        ExportFormat.MARKDOWN: markdown,
        ExportFormat.DOCX: docx,
        ExportFormat.PDF: pdf,
        ExportFormat.LATEX: latex,
    }[data.format]
    body = await asyncio.to_thread(renderer, manuscript.title, resolved, references)
    export = ManuscriptExport(
        project_id=project_id,
        manuscript_version_id=manuscript.current_version_id,
        citation_style=data.citation_style,
        export_format=data.format,
        status=ExportStatus.RUNNING,
    )
    session.add(export)
    await session.flush()
    extension = {
        ExportFormat.MARKDOWN: "md",
        ExportFormat.DOCX: "docx",
        ExportFormat.PDF: "pdf",
        ExportFormat.LATEX: "tex",
    }[data.format]
    key = (
        f"projects/{project_id}/manuscripts/{manuscript.current_version_id}"
        f"/exports/{export.id}.{extension}"
    )
    content_type = {
        ExportFormat.MARKDOWN: "text/markdown",
        ExportFormat.DOCX: (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        ExportFormat.PDF: "application/pdf",
        ExportFormat.LATEX: "application/x-tex",
    }[data.format]
    await object_storage().put(key, body, content_type)
    export.status = ExportStatus.COMPLETED
    export.artifact_location = key
    export.generated_at = datetime.now(UTC)
    return {
        "id": export.id,
        "status": export.status,
        "format": export.export_format,
        "citation_style": export.citation_style,
        "size": len(body),
        "metadata_warnings": warnings,
    }


@router.get("/{project_id}/exports")
async def list_exports(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    rows = list(
        await session.scalars(
            select(ManuscriptExport)
            .where(ManuscriptExport.project_id == project_id)
            .order_by(ManuscriptExport.created_at.desc())
        )
    )
    return [
        {
            "id": row.id,
            "status": row.status,
            "format": row.export_format,
            "citation_style": row.citation_style,
            "generated_at": row.generated_at,
        }
        for row in rows
    ]


@router.get("/{project_id}/exports/{export_id}/download")
async def download_export(
    project_id: uuid.UUID, export_id: uuid.UUID, session: DB, user: Principal
) -> Response:
    await scoped_project(session, user, project_id)
    row = await session.get(ManuscriptExport, export_id)
    if row is None or row.project_id != project_id or not row.artifact_location:
        raise error(404, "NOT_FOUND", "Export not found")
    body = await object_storage().get(row.artifact_location)
    media_type = {
        ExportFormat.MARKDOWN: "text/markdown",
        ExportFormat.DOCX: (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        ExportFormat.PDF: "application/pdf",
        ExportFormat.LATEX: "application/x-tex",
    }[row.export_format]
    extension = {
        ExportFormat.MARKDOWN: "md",
        ExportFormat.DOCX: "docx",
        ExportFormat.PDF: "pdf",
        ExportFormat.LATEX: "tex",
    }[row.export_format]
    return Response(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="manuscript-v{row.manuscript_version_id}.{extension}"'
            )
        },
    )

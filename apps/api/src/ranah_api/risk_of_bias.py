import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import Field, model_validator
from ranah_agents.risk_of_bias import TOOL_VERSION, TOOLS, select_tool
from ranah_domain.enums import StudyStatus
from ranah_domain.models.risk_of_bias import RiskOfBiasAssessment, RiskOfBiasDomain
from ranah_domain.models.study import Study
from ranah_domain.repositories.fulltext import chunks_for, latest_parsed_document
from ranah_domain.repositories.screening import final_included_work_ids, latest_protocol
from ranah_domain.repositories.study import works_for_study
from ranah_domain.schemas.screening import StrictModel, Text
from sqlalchemy import func, select

from ranah_api.projects import DB, Principal, append_event, error, scoped_project, start_operation

router = APIRouter(prefix="/projects", tags=["Risk of bias"])
Judgement = Literal["LOW_RISK", "SOME_CONCERNS", "HIGH_RISK", "UNASSESSED"]


class HumanDomain(StrictModel):
    domain_code: str
    judgement: Judgement
    rationale: Text
    supporting_evidence: str = ""
    work_id: uuid.UUID | None = None
    page: int | None = Field(default=None, ge=1)


class HumanAssessment(StrictModel):
    overall_judgement: Literal["LOW_RISK", "SOME_CONCERNS", "HIGH_RISK", "NOT_ASSESSED"]
    domains: list[HumanDomain] = Field(min_length=1)

    @model_validator(mode="after")
    def complete(self) -> "HumanAssessment":
        if any(d.judgement == "UNASSESSED" for d in self.domains):
            raise ValueError("Approval requires a judgement for every domain")
        if self.overall_judgement == "NOT_ASSESSED":
            raise ValueError("Approval requires an overall judgement")
        return self


async def assessment_view(session: DB, assessment: RiskOfBiasAssessment) -> dict[str, Any]:
    domains = list(
        await session.scalars(
            select(RiskOfBiasDomain)
            .where(RiskOfBiasDomain.assessment_id == assessment.id)
            .order_by(RiskOfBiasDomain.domain_code)
        )
    )
    return {
        "id": assessment.id,
        "study_id": assessment.study_id,
        "version": assessment.version,
        "tool": assessment.tool,
        "tool_version": assessment.tool_version,
        "overall_judgement": assessment.overall_judgement,
        "status": assessment.status,
        "reviewer_id": assessment.reviewer_id,
        "agent_run_id": assessment.agent_run_id,
        "created_at": assessment.created_at,
        "domains": [
            {
                "domain_code": d.domain_code,
                "judgement": d.judgement,
                "rationale": d.rationale,
                "supporting_evidence": d.supporting_evidence,
                "work_id": d.work_id,
                "page": d.page,
            }
            for d in domains
        ],
    }


@router.get("/{project_id}/risk-of-bias")
async def list_assessments(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    await scoped_project(session, user, project_id)
    rows = list(
        await session.scalars(
            select(RiskOfBiasAssessment)
            .where(RiskOfBiasAssessment.project_id == project_id)
            .order_by(RiskOfBiasAssessment.study_id, RiskOfBiasAssessment.version.desc())
        )
    )
    return [await assessment_view(session, row) for row in rows]


@router.post("/{project_id}/risk-of-bias/start", status_code=202)
async def start_assessment(project_id: uuid.UUID, session: DB, user: Principal) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    protocol = await latest_protocol(session, project_id)
    if protocol is None or not await final_included_work_ids(session, protocol.id):
        raise error(
            409, "WORKFLOW_CONFLICT", "Complete full-text screening before risk-of-bias assessment"
        )
    return await start_operation(session, project, "risk_of_bias", {})


@router.post("/{project_id}/studies/{study_id}/risk-of-bias/review", status_code=201)
async def review_assessment(
    project_id: uuid.UUID, study_id: uuid.UUID, data: HumanAssessment, session: DB, user: Principal
) -> Any:
    project = await scoped_project(session, user, project_id, write=True)
    study = await session.get(Study, study_id)
    if study is None or study.project_id != project_id or study.status == StudyStatus.MERGED:
        raise error(404, "NOT_FOUND", "Study not found in this project")
    tool = select_tool(study.study_type)
    if tool is None:
        raise error(
            409, "WORKFLOW_CONFLICT", "No supported risk-of-bias tool for this study design"
        )
    protocol = await latest_protocol(session, project_id)
    included = set(await final_included_work_ids(session, protocol.id)) if protocol else set()
    if len(data.domains) != len(TOOLS[tool]) or {d.domain_code for d in data.domains} != set(
        TOOLS[tool]
    ):
        raise error(422, "USER_INPUT_ERROR", "Provide exactly one judgement for each tool domain")
    links = {link.work_id for link in await works_for_study(session, study.id)}
    if not links & included:
        raise error(409, "WORKFLOW_CONFLICT", "Study is not in the final included corpus")
    for domain in data.domains:
        if not domain.supporting_evidence or domain.work_id not in links or domain.page is None:
            raise error(
                422, "USER_INPUT_ERROR", "Every domain needs a quote, linked publication, and page"
            )
        document = await latest_parsed_document(session, domain.work_id)
        if document is None or not any(
            domain.supporting_evidence in chunk.text
            and chunk.page_start <= domain.page <= chunk.page_end
            for chunk in await chunks_for(session, document.id)
        ):
            raise error(422, "USER_INPUT_ERROR", "Domain quote must appear on its cited page")
    current_version = await session.scalar(
        select(func.max(RiskOfBiasAssessment.version)).where(
            RiskOfBiasAssessment.study_id == study.id
        )
    )
    row = RiskOfBiasAssessment(
        project_id=project_id,
        study_id=study.id,
        version=(current_version or 0) + 1,
        tool=tool,
        tool_version=TOOL_VERSION,
        overall_judgement=data.overall_judgement,
        status="APPROVED",
        reviewer_id=user.id,
    )
    session.add(row)
    await session.flush()
    for domain in data.domains:
        session.add(
            RiskOfBiasDomain(
                assessment_id=row.id,
                domain_code=domain.domain_code,
                judgement=domain.judgement,
                rationale=domain.rationale,
                supporting_evidence=domain.supporting_evidence,
                work_id=domain.work_id,
                page=domain.page,
            )
        )
    append_event(
        session,
        project,
        user,
        "RISK_OF_BIAS_REVIEWED",
        study_id=str(study_id),
        assessment_id=str(row.id),
    )
    await session.flush()
    return await assessment_view(session, row)

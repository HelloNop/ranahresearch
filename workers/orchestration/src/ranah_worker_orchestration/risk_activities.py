"""Create tentative appraisals from retrieved study passages."""

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.evidence import ExtractionPassage
from ranah_agents.risk_of_bias import (
    TOOL_VERSION,
    TOOLS,
    RiskInput,
    RiskOutput,
    risk_registry,
    select_tool,
)
from ranah_agents.runtime import run_agent
from ranah_agents.tools import ToolRegistry
from ranah_documents.retrieval import select_passages
from ranah_domain.db import session_scope
from ranah_domain.enums import AgentRunStatus, StudyStatus
from ranah_domain.models.risk_of_bias import RiskOfBiasAssessment, RiskOfBiasDomain
from ranah_domain.models.study import Study
from ranah_domain.repositories.fulltext import chunks_for, latest_parsed_document
from ranah_domain.repositories.screening import final_included_work_ids, latest_protocol
from ranah_domain.repositories.study import works_for_study
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research


@activity.defn
async def assess_risk_of_bias(operation_id: str) -> dict[str, int]:
    counts = {"assessed": 0, "unsupported": 0, "awaiting_source": 0, "failed": 0}
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        protocol = await latest_protocol(session, op.project_id)
        if protocol is None:
            raise ApplicationError("An approved protocol is required", non_retryable=True)
        included = set(await final_included_work_ids(session, protocol.id))
        study_ids = list(
            await session.scalars(
                select(Study.id).where(
                    Study.project_id == op.project_id, Study.status != StudyStatus.MERGED
                )
            )
        )

    for study_id in study_ids:
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            study = await session.get(Study, study_id)
            assert study is not None
            links = await works_for_study(session, study.id)
            if not any(link.work_id in included for link in links):
                continue
            tool = select_tool(study.study_type)
            if tool is None:
                counts["unsupported"] += 1
                continue
            previous = await session.scalar(
                select(RiskOfBiasAssessment)
                .where(RiskOfBiasAssessment.study_id == study.id)
                .order_by(RiskOfBiasAssessment.version.desc())
                .limit(1)
            )
            if previous is not None and previous.tool == tool:
                continue

            passages: list[ExtractionPassage] = []
            for link in links:
                document = await latest_parsed_document(session, link.work_id)
                if document is None:
                    continue
                chunks = await chunks_for(session, document.id)
                selected = select_passages(
                    chunks,
                    [
                        "random",
                        "allocation",
                        "blinding",
                        "confound",
                        "selection",
                        "missing",
                        "outcome",
                        "measurement",
                        "report",
                    ],
                    limit=20,
                    prefer_sections=("METHODS", "RESULTS"),
                )
                for chunk in selected:
                    passages.append(
                        ExtractionPassage(
                            passage_id=len(passages) + 1,
                            work_id=link.work_id,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            section_path=chunk.section_path,
                            section_type=chunk.section_type,
                            text=chunk.text,
                        )
                    )
            if not passages:
                counts["awaiting_source"] += 1
                continue

            payload = RiskInput(
                study_id=study.id,
                study_label=study.study_label,
                study_type=study.study_type,
                tool=tool,
                domains=list(TOOLS[tool]),
                passages=passages[:24],
            )
            result = await run_agent(
                session,
                risk_registry(),
                ContextBuilder(ToolRegistry(), research.gateway()),
                name="risk_of_bias_agent",
                version="1",
                project_id=op.project_id,
                task=AgentTask(
                    task_type="risk_of_bias_agent", payload=payload.model_dump(mode="json")
                ),
                workflow_id=op.temporal_workflow_id,
            )
            if result.status not in (
                AgentRunStatus.SUCCESS,
                AgentRunStatus.NEEDS_HUMAN,
            ) or not isinstance(result.structured_output, RiskOutput):
                counts["failed"] += 1
                continue
            output = result.structured_output
            assessment = RiskOfBiasAssessment(
                project_id=op.project_id,
                study_id=study.id,
                version=previous.version + 1 if previous else 1,
                tool=tool,
                tool_version=TOOL_VERSION,
                overall_judgement=output.overall_judgement,
                status="NEEDS_REVIEW" if output.requires_human else "PROPOSED",
                agent_run_id=result.agent_run_id,
            )
            session.add(assessment)
            await session.flush()
            passage_by_id = {p.passage_id: p for p in passages}
            for item in output.domain_assessments:
                source = passage_by_id.get(item.passage_id or -1)
                session.add(
                    RiskOfBiasDomain(
                        assessment_id=assessment.id,
                        domain_code=item.domain_code,
                        judgement=item.judgement,
                        rationale=item.rationale,
                        supporting_evidence=item.supporting_evidence,
                        work_id=source.work_id if source else None,
                        page=source.page_start if source else None,
                    )
                )
            counts["assessed"] += 1
            research.event(
                session,
                op.project_id,
                "RISK_OF_BIAS_PROPOSED",
                study_id=str(study.id),
                assessment_id=str(assessment.id),
                tool=tool,
            )

    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        op.details = {**op.details, "progress": counts}
    return counts

import uuid
from typing import cast

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.research import FrameworkOutput, PlanOutput
from ranah_agents.runtime import run_agent
from ranah_agents.screening import (
    DiscoverySummary,
    ProtocolInput,
    ProtocolOutput,
    ScreeningInput,
    ScreeningOutput,
    screening_registry,
)
from ranah_agents.tools import ToolRegistry
from ranah_domain.db import session_scope
from ranah_domain.enums import AgentRunStatus
from ranah_domain.models.project import ResearchFramework, ResearchPlan
from ranah_domain.models.screening import EligibilityCriterion, ReviewProtocol, ScreeningDecision
from ranah_domain.models.search import SearchRun
from ranah_domain.models.work import WorkMetadataObservation, WorkRecord
from ranah_domain.repositories.screening import (
    canonical_ids,
    criteria_for,
    effective_decisions,
    progress,
)
from ranah_domain.schemas.screening import evaluate
from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration import activities
from ranah_worker_orchestration import research_activities as research


@activity.defn
async def generate_protocol(operation_id: str) -> None:
    failed = False
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        if op.details.get("protocol_id"):
            return
        plan = await session.get(ResearchPlan, uuid.UUID(str(op.details["plan_id"])))
        framework = await session.get(ResearchFramework, uuid.UUID(str(op.details["framework_id"])))
        if not plan or not framework or plan.status != "APPROVED":
            raise ApplicationError("Approved plan and framework required", non_retryable=True)
        runs = list(
            await session.scalars(select(SearchRun).where(SearchRun.project_id == op.project_id))
        )
        plan_data = PlanOutput.model_validate(plan.content)
        payload = ProtocolInput(
            plan_id=plan.id,
            plan_version=plan.version,
            plan=plan_data,
            research_question=plan_data.recommended_research_question,
            framework_id=framework.id,
            framework=FrameworkOutput.model_validate(framework.structured_elements),
            review_method=plan_data.recommended_review_method,
            user_constraints=op.details.get("user_constraints"),  # type: ignore[arg-type]
            discovery=DiscoverySummary(
                canonical_records=len(await canonical_ids(session, op.project_id)),
                information_sources=sorted({run.provider for run in runs}),
                partial=any(run.status != "COMPLETED" for run in runs),
            ),
        )
        result = await run_agent(
            session,
            screening_registry(),
            ContextBuilder(ToolRegistry(), research.gateway()),
            name="protocol_agent",
            version="1",
            project_id=op.project_id,
            task=AgentTask(task_type="protocol_agent", payload=payload.model_dump(mode="json")),
            workflow_id=op.temporal_workflow_id,
        )
        if result.status != AgentRunStatus.SUCCESS or not isinstance(
            result.structured_output, ProtocolOutput
        ):
            failed = True
        else:
            values = result.structured_output.model_dump(mode="json")
            criteria = values.pop("eligibility_criteria")
            protocol = ReviewProtocol(
                project_id=op.project_id,
                research_plan_id=plan.id,
                framework_id=framework.id,
                research_question=payload.research_question,
                version=1,
                status="PROPOSED",
                created_by_agent_run_id=result.agent_run_id,
                **values,
            )
            session.add(protocol)
            await session.flush()
            session.add_all([EligibilityCriterion(protocol_id=protocol.id, **c) for c in criteria])
            op.details = {**op.details, "protocol_id": str(protocol.id)}
            research.event(
                session, op.project_id, "PROTOCOL_PROPOSED", protocol_id=str(protocol.id)
            )
    if failed:
        raise ApplicationError(
            "Protocol generation failed validation; inspect agent run", non_retryable=True
        )


@activity.defn
async def prepare_screening_batch(operation_id: str) -> list[str]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        protocol = await session.get(ReviewProtocol, uuid.UUID(str(op.details["protocol_id"])))
        if not protocol or protocol.status != "APPROVED":
            raise ApplicationError("Approved protocol required", non_retryable=True)
        effective = await effective_decisions(session, protocol.id)
        return [
            str(key)
            for key in cast(list[str], op.details["work_ids"])
            if uuid.UUID(str(key)) not in effective
        ][: int(str(op.details["batch_size"]))]


@activity.defn
async def run_screening_batch(operation_id: str, work_ids: list[str]) -> None:
    for work_id in work_ids:
        failed = False
        async with session_scope(activities._session_factory()) as session:
            op = await research.operation(session, operation_id)
            pid = uuid.UUID(str(op.details["protocol_id"]))
            wid = uuid.UUID(work_id)
            if wid in await effective_decisions(session, pid):
                continue
            protocol = await session.get(ReviewProtocol, pid)
            work = await session.get(WorkRecord, wid)
            if not protocol or not work or work.project_id != op.project_id:
                raise ApplicationError("Invalid screening inputs", non_retryable=True)
            criteria = await criteria_for(session, pid)
            metadata = {
                field: getattr(work, field)
                for field in ("publication_year", "language", "publication_type")
            }
            observations = list(
                await session.scalars(
                    select(WorkMetadataObservation).where(WorkMetadataObservation.work_id == wid)
                )
            )
            trusted: set[str] = set()
            for field, value in metadata.items():
                observations_for_field = [
                    o
                    for o in observations
                    if o.field_name == field and o.field_value.get("value") is not None
                ]
                # Identity verification alone does not establish field-level agreement.
                if (
                    value is not None
                    and len({o.provider for o in observations_for_field}) >= 2
                    and all(o.field_value.get("value") == value for o in observations_for_field)
                ):
                    trusted.add(field)
            payload = ScreeningInput(
                work_id=wid,
                title=work.title,
                abstract=work.abstract,
                publication_year=work.publication_year,
                language=work.language,
                publication_type=work.publication_type,
                protocol_id=pid,
                protocol_version=protocol.version,
                research_question=protocol.research_question,
                eligibility_criteria=criteria,
                deterministic_assessments=[evaluate(c, metadata, trusted) for c in criteria],
            )
            result = await run_agent(
                session,
                screening_registry(),
                ContextBuilder(ToolRegistry(), research.gateway()),
                name="screening_agent",
                version="1",
                project_id=op.project_id,
                task=AgentTask(
                    task_type="screening_agent", payload=payload.model_dump(mode="json")
                ),
                workflow_id=op.temporal_workflow_id,
            )
            if result.status != AgentRunStatus.SUCCESS or not isinstance(
                result.structured_output, ScreeningOutput
            ):
                failed = True
            else:
                decision = ScreeningDecision(
                    project_id=op.project_id,
                    work_id=wid,
                    protocol_id=pid,
                    protocol_version=protocol.version,
                    round_id=op.id,
                    stage="TITLE_ABSTRACT",
                    reviewer_type="AI",
                    agent_run_id=result.agent_run_id,
                    **result.structured_output.model_dump(mode="json"),
                )
                session.add(decision)
                research.event(
                    session,
                    op.project_id,
                    "SCREENING_AI_DECISION",
                    work_id=work_id,
                    protocol_version=protocol.version,
                    agent_run_id=str(result.agent_run_id),
                )
        if failed:
            raise ApplicationError("Screening agent failed; persisted decisions are preserved")


@activity.defn
async def calculate_screening_progress(operation_id: str) -> dict[str, int]:
    async with session_scope(activities._session_factory()) as session:
        op = await research.operation(session, operation_id)
        counts = await progress(
            session,
            uuid.UUID(str(op.details["protocol_id"])),
            [uuid.UUID(str(i)) for i in cast(list[str], op.details["work_ids"])],
        )
        op.details = {**op.details, "progress": counts}
        return counts

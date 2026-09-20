import os
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel
from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.research import (
    DirectorInput,
    FrameworkInput,
    FrameworkOutput,
    PlanOutput,
    SearchFilters,
    StrategyInput,
    StrategyOutput,
    research_registry,
)
from ranah_agents.runtime import run_agent
from ranah_agents.tools import ToolRegistry
from ranah_domain.db import session_scope
from ranah_domain.enums import (
    AgentRunStatus,
    ProjectEventActorType,
    ProjectStatus,
    ResearchPlanStatus,
    SearchArtifactStatus,
    WorkflowRunStatus,
)
from ranah_domain.models.events import ProjectEvent
from ranah_domain.models.project import (
    ResearchFramework,
    ResearchIdea,
    ResearchPlan,
    ResearchProject,
    ResearchQuestion,
)
from ranah_domain.models.search import SearchQuery, SearchStrategy
from ranah_domain.models.workflow import WorkflowRun
from ranah_llm.gateway import LLMGateway
from ranah_llm.providers.openai import OpenAIProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ranah_worker_orchestration.activities import _session_factory


@lru_cache
def gateway() -> LLMGateway:
    return LLMGateway(
        {"openai": OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])},
        ModelRouter(
            {
                ModelTier.STANDARD: RoutedModel(
                    provider="openai", model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
                ),
                # Extraction reads numbers off a page, where a cheaper model's
                # transcription slips are expensive to catch downstream.
                ModelTier.HIGH_PRECISION_EXTRACTION: RoutedModel(
                    provider="openai",
                    model=os.environ.get("OPENAI_EXTRACTION_MODEL", "gpt-4o"),
                ),
            }
        ),
    )


def event(session: AsyncSession, project_id: uuid.UUID, name: str, **payload: Any) -> None:
    session.add(
        ProjectEvent(
            project_id=project_id,
            event_type=name,
            actor_type=ProjectEventActorType.SYSTEM,
            payload=payload,
        )
    )


async def operation(session: AsyncSession, operation_id: str) -> WorkflowRun:
    row = await session.get(WorkflowRun, uuid.UUID(operation_id), with_for_update=True)
    if row is None:
        raise ApplicationError("Operation not found", non_retryable=True)
    return row


@activity.defn
async def set_operation_stage(operation_id: str, stage: str) -> None:
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        if row.stage != stage:
            row.stage = stage
            row.status = WorkflowRunStatus.RUNNING
            event(session, row.project_id, stage, operation_id=operation_id)


@activity.defn
async def finish_operation(operation_id: str, status: str, error: str | None = None) -> None:
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        if row.completed_at:
            return
        row.status = WorkflowRunStatus(status)
        row.stage = status
        row.completed_at = datetime.now(UTC)
        row.details = {**row.details, "error": error}
        project = await session.get(ResearchProject, row.project_id)
        if project and row.workflow_type == "ResearchDiscoveryWorkflow":
            project.status = ProjectStatus.EXPLORATION
        event(
            session,
            row.project_id,
            {
                "ResearchDiscoveryWorkflow": "DISCOVERY_COMPLETED",
                "ProtocolWorkflow": "PROTOCOL_GENERATION_COMPLETED",
                "TitleAbstractScreeningWorkflow": "SCREENING_ROUND_COMPLETED",
            }.get(row.workflow_type, "PLANNING_COMPLETED"),
            operation_id=operation_id,
            status=status,
            error=error,
        )


@activity.defn
async def generate_research_artifact(operation_id: str, agent_name: str) -> str:
    failure = False
    artifact_id = ""
    async with session_scope(_session_factory()) as session:
        row = await operation(session, operation_id)
        if agent_name in row.details:
            return str(row.details[agent_name])
        project = await session.get(ResearchProject, row.project_id, with_for_update=True)
        assert project is not None
        plan: ResearchPlan | None = None
        framework: ResearchFramework | None = None
        payload: BaseModel
        if agent_name == "research_director":
            idea = await session.get(ResearchIdea, uuid.UUID(str(row.details["idea_id"])))
            assert idea is not None and idea.project_id == project.id
            payload = DirectorInput(
                project_id=project.id, raw_idea=idea.raw_text, existing_project_title=project.title
            )
        else:
            plan_id = row.details.get("research_director", row.details.get("plan_id"))
            plan = await session.get(ResearchPlan, uuid.UUID(str(plan_id)))
            assert plan is not None and plan.project_id == project.id
            plan_output = PlanOutput.model_validate(plan.content)
            if agent_name == "framework_selector":
                payload = FrameworkInput(
                    research_objective=plan_output.research_objective,
                    recommended_research_question=plan_output.recommended_research_question,
                    review_method=plan_output.recommended_review_method,
                    key_concepts=plan_output.key_concepts,
                    domain_context=plan_output.scope,
                )
            else:
                if plan.status != ResearchPlanStatus.APPROVED:
                    raise ApplicationError("Plan approval required", non_retryable=True)
                framework = await session.scalar(
                    select(ResearchFramework).where(ResearchFramework.research_plan_id == plan.id)
                )
                assert framework is not None
                payload = StrategyInput(
                    plan=plan_output,
                    framework=FrameworkOutput.model_validate(framework.structured_elements),
                    target_providers=["crossref", "openalex", "semantic_scholar"],
                    filters=SearchFilters.model_validate(row.details.get("filters", {})),
                )
        result = await run_agent(
            session,
            research_registry(),
            ContextBuilder(ToolRegistry(), gateway()),
            name=agent_name,
            version="1",
            project_id=project.id,
            task=AgentTask(task_type=agent_name, payload=payload.model_dump(mode="json")),
            workflow_id=row.temporal_workflow_id,
        )
        if result.status != AgentRunStatus.SUCCESS:
            failure = True
        elif isinstance(result.structured_output, PlanOutput):
            output = result.structured_output
            version = (
                await session.scalar(
                    select(func.max(ResearchPlan.version)).where(
                        ResearchPlan.project_id == project.id
                    )
                )
                or 0
            ) + 1
            plan = ResearchPlan(
                project_id=project.id,
                version=version,
                status=ResearchPlanStatus.PROPOSED,
                research_idea_id=uuid.UUID(str(row.details["idea_id"])),
                content=output.model_dump(mode="json"),
                provisional_title=output.provisional_title,
                problem_statement=output.problem_statement,
                objective=output.research_objective,
                scope_summary=output.scope,
                recommended_method=output.recommended_review_method,
                recommended_framework=output.recommended_framework,
                rationale=output.rationale,
                created_by_agent_run_id=result.agent_run_id,
            )
            session.add(plan)
            await session.flush()
            questions = list(
                dict.fromkeys(
                    [output.recommended_research_question, *output.candidate_research_questions]
                )
            )
            for position, question in enumerate(questions):
                session.add(
                    ResearchQuestion(
                        project_id=project.id,
                        research_plan_id=plan.id,
                        question_type="REVIEW",
                        question_text=question,
                        is_primary=position == 0,
                        position=position,
                    )
                )
            project.status = ProjectStatus.PLANNING
            artifact_id = str(plan.id)
            event(session, project.id, "RESEARCH_PLAN_GENERATED", plan_id=artifact_id)
        elif isinstance(result.structured_output, FrameworkOutput):
            assert plan is not None
            framework_output = result.structured_output
            framework = ResearchFramework(
                project_id=project.id,
                research_plan_id=plan.id,
                version=plan.version,
                framework_type=framework_output.framework_type,
                structured_elements=framework_output.model_dump(mode="json"),
                rationale=framework_output.rationale,
                created_by_agent_run_id=result.agent_run_id,
            )
            session.add(framework)
            await session.flush()
            artifact_id = str(framework.id)
            event(session, project.id, "FRAMEWORK_SELECTED", framework_id=artifact_id)
        elif isinstance(result.structured_output, StrategyOutput):
            assert plan is not None and framework is not None
            strategy_output = result.structured_output
            version = (
                await session.scalar(
                    select(func.max(SearchStrategy.version)).where(
                        SearchStrategy.project_id == project.id
                    )
                )
                or 0
            ) + 1
            strategy = SearchStrategy(
                project_id=project.id,
                research_plan_id=plan.id,
                research_framework_id=framework.id,
                version=version,
                content=strategy_output.model_dump(mode="json"),
                description=strategy_output.rationale,
                created_by_agent_run_id=result.agent_run_id,
                status=SearchArtifactStatus.APPROVED,
            )
            session.add(strategy)
            await session.flush()
            for query in strategy_output.provider_queries:
                session.add(
                    SearchQuery(
                        search_strategy_id=strategy.id,
                        provider=query.provider,
                        query_text=query.query_text,
                        filters=strategy_output.filters.model_dump(),
                        status=SearchArtifactStatus.APPROVED,
                    )
                )
            artifact_id = str(strategy.id)
            event(session, project.id, "SEARCH_STRATEGY_CREATED", strategy_id=artifact_id)
        if artifact_id:
            row.details = {**row.details, agent_name: artifact_id}
    if failure:
        raise ApplicationError(
            "INVALID_AGENT_OUTPUT: planning failed; retry is available", non_retryable=True
        )
    return artifact_id

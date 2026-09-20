"""EPIC-007 acceptance tests: registry, tool permissions, validation, persistence, failures."""

import uuid

import pytest
from pydantic import BaseModel
from ranah_agents import (
    AgentContext,
    AgentRegistry,
    AgentResult,
    AgentTask,
    ContextBuilder,
    ToolPermissionError,
    ToolRegistry,
    run_agent,
)
from ranah_agents.sample_agent import CONTRACT, SampleAgentOutput, execute
from ranah_domain.enums import AgentRunStatus
from ranah_domain.repositories import agents as agents_repo
from ranah_domain.repositories import organizations as organizations_repo
from ranah_domain.repositories import projects as projects_repo
from ranah_domain.schemas.organization import OrganizationCreate
from ranah_domain.schemas.project import ResearchProjectCreate
from ranah_llm.gateway import LLMGateway
from ranah_llm.providers.fake import FakeLLMProvider
from ranah_llm.routing import ModelRouter, ModelTier, RoutedModel
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_project(session: AsyncSession) -> uuid.UUID:
    org = await organizations_repo.create_organization(
        session, OrganizationCreate(name="Agent test org", slug=f"agent-{uuid.uuid4().hex[:8]}")
    )
    project = await projects_repo.create_project(
        session, ResearchProjectCreate(organization_id=org.id, title="Agent test project")
    )
    return project.id


def _gateway(provider: FakeLLMProvider) -> LLMGateway:
    router = ModelRouter({ModelTier.FAST: RoutedModel(provider="fake", model="fake-1")})
    return LLMGateway({"fake": provider}, router)


def _registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(CONTRACT, execute)
    return registry


async def test_registry_and_declared_tools() -> None:
    tools = ToolRegistry()

    async def echo_tool(x: str) -> str:
        return x

    tools.register("echo", echo_tool)
    scoped = tools.scoped_to(("echo",))
    assert await scoped.call("echo", "hi") == "hi"

    with pytest.raises(ToolPermissionError):
        await scoped.call("other_tool")


async def test_sample_agent_run_persists_success(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    provider = FakeLLMProvider(structured_response={"answer": "42", "confidence": 0.9})
    context_builder = ContextBuilder(ToolRegistry(), _gateway(provider))

    result = await run_agent(
        db_session,
        _registry(),
        context_builder,
        name="sample_agent",
        version="v1",
        project_id=project_id,
        task=AgentTask(task_type="ANSWER_QUESTION", payload={"question": "What is 6*7?"}),
    )

    assert result.status == AgentRunStatus.SUCCESS
    assert isinstance(result.structured_output, SampleAgentOutput)
    assert result.structured_output.answer == "42"

    definition = await agents_repo.get_by_name_version(db_session, "sample_agent", "v1")
    assert definition is not None


async def test_invalid_input_is_rejected_before_execution(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)
    provider = FakeLLMProvider()
    context_builder = ContextBuilder(ToolRegistry(), _gateway(provider))

    result = await run_agent(
        db_session,
        _registry(),
        context_builder,
        name="sample_agent",
        version="v1",
        project_id=project_id,
        # Missing the required "question" field.
        task=AgentTask(task_type="ANSWER_QUESTION", payload={}),
    )

    assert result.status == AgentRunStatus.INVALID_INPUT
    assert provider.calls == []


async def test_invalid_structured_output_fails_run(db_session: AsyncSession) -> None:
    """An executor that returns the wrong shape gets caught by the runtime's own check,
    independent of whatever validation the LLM gateway already did."""
    project_id = await _make_project(db_session)

    class MismatchedOutput(BaseModel):
        only_this_field: str

    async def wrong_shape_executor(context: AgentContext, data: object) -> AgentResult:
        return AgentResult(
            status=AgentRunStatus.SUCCESS,
            structured_output=MismatchedOutput(only_this_field="x"),
        )

    registry = AgentRegistry()
    registry.register(CONTRACT, wrong_shape_executor)
    context_builder = ContextBuilder(ToolRegistry(), _gateway(FakeLLMProvider()))

    result = await run_agent(
        db_session,
        registry,
        context_builder,
        name="sample_agent",
        version="v1",
        project_id=project_id,
        task=AgentTask(task_type="ANSWER_QUESTION", payload={"question": "What is 6*7?"}),
    )

    assert result.status == AgentRunStatus.FAILED
    assert result.error_code == "INVALID_OUTPUT_SCHEMA"


async def test_executor_crash_is_recorded_as_failed(db_session: AsyncSession) -> None:
    project_id = await _make_project(db_session)

    async def crashing_executor(context: AgentContext, data: object) -> AgentResult:
        raise RuntimeError("boom")

    registry = AgentRegistry()
    registry.register(CONTRACT, crashing_executor)
    context_builder = ContextBuilder(ToolRegistry(), _gateway(FakeLLMProvider()))

    result = await run_agent(
        db_session,
        registry,
        context_builder,
        name="sample_agent",
        version="v1",
        project_id=project_id,
        task=AgentTask(task_type="ANSWER_QUESTION", payload={"question": "hi"}),
    )

    assert result.status == AgentRunStatus.FAILED
    assert result.error_code == "EXECUTOR_ERROR"

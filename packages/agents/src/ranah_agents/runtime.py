"""Ties contract, context, execution, and AgentRun persistence into one call.

Every run is reproducible from the AgentRun row this writes: agent name/version,
task type, status, model, prompt version, input/output metadata, timing, tokens,
and error code (docs/AGENT_CONTRACTS.md #4, #81, #91).
"""

import uuid

from pydantic import ValidationError
from ranah_domain.enums import AgentRunStatus
from ranah_domain.repositories import agents as agents_repo
from ranah_domain.schemas.agent import AgentDefinitionCreate, AgentRunComplete, AgentRunCreate
from sqlalchemy.ext.asyncio import AsyncSession

from ranah_agents.context import AgentTask, ContextBuilder
from ranah_agents.registry import AgentRegistry
from ranah_agents.results import AgentResult


async def run_agent(
    session: AsyncSession,
    registry: AgentRegistry,
    context_builder: ContextBuilder,
    *,
    name: str,
    version: str,
    project_id: uuid.UUID,
    task: AgentTask,
    workflow_id: str | None = None,
) -> AgentResult:
    registered = registry.get(name, version)
    contract = registered.contract

    definition = await agents_repo.get_or_create_definition(
        session,
        AgentDefinitionCreate(
            name=contract.name,
            version=contract.version,
            description=contract.purpose,
            input_schema=contract.input_schema.model_json_schema(),
            output_schema=contract.output_schema.model_json_schema(),
            prompt_version=contract.prompt_version,
        ),
    )

    try:
        validated_input = contract.input_schema.model_validate(task.payload)
    except ValidationError as exc:
        return await _record(
            session,
            project_id,
            definition.id,
            workflow_id,
            task,
            contract.prompt_version,
            AgentResult(
                status=AgentRunStatus.INVALID_INPUT,
                error_code="INVALID_INPUT_SCHEMA",
                warnings=[str(exc)],
            ),
        )

    run = await agents_repo.start_agent_run(
        session,
        AgentRunCreate(
            project_id=project_id,
            agent_definition_id=definition.id,
            workflow_id=workflow_id,
            task_type=task.task_type,
            prompt_version=contract.prompt_version,
            input_metadata=task.payload,
        ),
    )

    context = await context_builder.build(
        contract, project_id=str(project_id), agent_run_id=str(run.id)
    )

    try:
        result = await registered.executor(context, validated_input)
    except Exception as exc:  # noqa: BLE001 - an agent crashing must not crash the runtime
        result = AgentResult(
            status=AgentRunStatus.FAILED, error_code="EXECUTOR_ERROR", warnings=[str(exc)]
        )

    if result.structured_output is not None:
        try:
            contract.output_schema.model_validate(result.structured_output.model_dump())
        except ValidationError as exc:
            result = AgentResult(
                status=AgentRunStatus.FAILED,
                error_code="INVALID_OUTPUT_SCHEMA",
                warnings=[str(exc)],
            )

    await agents_repo.complete_agent_run(
        session,
        run.id,
        AgentRunComplete(
            status=result.status,
            output_metadata=result.structured_output.model_dump()
            if result.structured_output
            else {},
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            estimated_cost=result.usage.estimated_cost,
            error_code=result.error_code,
        ),
    )
    return result


async def _record(
    session: AsyncSession,
    project_id: uuid.UUID,
    agent_definition_id: uuid.UUID,
    workflow_id: str | None,
    task: AgentTask,
    prompt_version: str,
    result: AgentResult,
) -> AgentResult:
    """Persists a run that never got to execute (e.g. invalid input)."""
    run = await agents_repo.start_agent_run(
        session,
        AgentRunCreate(
            project_id=project_id,
            agent_definition_id=agent_definition_id,
            workflow_id=workflow_id,
            task_type=task.task_type,
            prompt_version=prompt_version,
            input_metadata=task.payload,
        ),
    )
    await agents_repo.complete_agent_run(
        session,
        run.id,
        AgentRunComplete(status=result.status, error_code=result.error_code),
    )
    return result

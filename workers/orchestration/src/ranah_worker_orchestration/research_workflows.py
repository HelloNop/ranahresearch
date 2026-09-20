import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3)


async def call(name: str, *args: object):  # type: ignore[no-untyped-def]
    return await workflow.execute_activity(
        name,
        args=args,
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RETRY,
    )


@workflow.defn
class ResearchPlanningWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            names = (
                ["research_director", "framework_selector"]
                if kind == "plan"
                else ["search_strategist"]
            )
            for name in names:
                await call("set_operation_stage", operation_id, name.upper())
                await call("generate_research_artifact", operation_id, name)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("finish_operation", operation_id, "FAILED", str(exc.cause or exc))
            return "FAILED"


@workflow.defn
class ResearchDiscoveryWorkflow:
    @workflow.run
    async def run(
        self,
        operation_id: str,
        project_id: str,
        search_strategy_id: str,
        search_query_ids: list[str],
    ) -> str:
        try:
            await call(
                "validate_discovery", operation_id, project_id, search_strategy_id, search_query_ids
            )
            await call("set_operation_stage", operation_id, "SEARCHING")
            outcomes = await asyncio.gather(
                *[
                    call("execute_provider_search", operation_id, query_id)
                    for query_id in search_query_ids
                ],
                return_exceptions=True,
            )
            for query_id, outcome in zip(search_query_ids, outcomes, strict=True):
                if isinstance(outcome, BaseException):
                    detail = outcome.cause if isinstance(outcome, ActivityError) else outcome
                    await call("record_provider_failure", operation_id, query_id, str(detail))
            for stage, activity_name in [
                ("NORMALIZING", "normalize_discovery"),
                ("DEDUPLICATING", "deduplicate_discovery"),
                ("VERIFYING", "verify_discovery"),
            ]:
                await call("set_operation_stage", operation_id, stage)
                await call(activity_name, operation_id)
            return str(await call("finalize_discovery", operation_id))
        except ActivityError as exc:
            await call("finish_operation", operation_id, "FAILED", str(exc.cause or exc))
            return "FAILED"

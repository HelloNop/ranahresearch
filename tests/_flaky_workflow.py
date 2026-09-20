"""Minimal workflow/activity pair used only to demonstrate activity retry.

Kept import-light (no ranah_domain) because Temporal's workflow sandbox
re-imports the module that defines a workflow class to validate it; pulling
in SQLAlchemy/psycopg here would drag that heavy, non-deterministic-looking
import chain into the sandbox for no reason.
"""

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

attempts: dict[str, int] = {}


@activity.defn
async def flaky_activity(key: str) -> str:
    attempts[key] = attempts.get(key, 0) + 1
    if attempts[key] < 3:
        raise RuntimeError("transient failure")
    return "ok"


@workflow.defn
class FlakyWorkflow:
    @workflow.run
    async def run(self, key: str) -> str:
        result: str = await workflow.execute_activity(
            flaky_activity,
            key,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(milliseconds=1), maximum_attempts=5
            ),
        )
        return result

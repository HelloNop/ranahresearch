"""ResearchFoundationWorkflow: the minimal workflow/activity shape this platform
builds on, not a real scientific pipeline. Proves: activities, retry, workflow
identifiers, WorkflowRun persistence, progress query, a signal, and cancellation.
"""

import asyncio
from datetime import timedelta
from typing import Any

from ranah_workflow import DEFAULT_RETRY_POLICY, OperationProgress
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ranah_worker_orchestration import activities

_ACTIVITY_TIMEOUT = timedelta(seconds=30)


@workflow.defn
class ResearchFoundationWorkflow:
    def __init__(self) -> None:
        self._notes: list[str] = []
        self._progress = OperationProgress(
            status="RUNNING", step="STARTING", completed_steps=0, total_steps=3
        )

    @workflow.run
    async def run(self, project_id: str) -> dict[str, Any]:
        workflow_run_id = await workflow.execute_activity(
            activities.create_workflow_run,
            args=[project_id, workflow.info().workflow_id, "ResearchFoundationWorkflow"],
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )
        try:
            prepared = await workflow.execute_activity(
                activities.prepare_scope,
                project_id,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                heartbeat_timeout=timedelta(seconds=5),
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._progress = OperationProgress(
                status="RUNNING", step="PREPARED", completed_steps=1, total_steps=3
            )

            finalized = await workflow.execute_activity(
                activities.finalize_scope,
                prepared,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._progress = OperationProgress(
                status="RUNNING", step="FINALIZED", completed_steps=2, total_steps=3
            )

            await workflow.execute_activity(
                activities.update_workflow_run_status,
                args=[workflow_run_id, "COMPLETED"],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self._progress = OperationProgress(
                status="COMPLETED", step="DONE", completed_steps=3, total_steps=3
            )
            return {"workflow_run_id": workflow_run_id, "result": finalized, "notes": self._notes}
        except asyncio.CancelledError:
            # Once a workflow's cancellation has been requested, the SDK will not
            # schedule further new activities from within this run (by design: a
            # cancelled workflow should not keep doing new work). WorkflowRun stays
            # at whatever status it last had; a caller observing the cancellation
            # (or a reconciliation pass) is responsible for marking it CANCELLED.
            self._progress = OperationProgress(
                status="CANCELLED", step="CANCELLED", completed_steps=0, total_steps=3
            )
            raise

    @workflow.signal
    def add_note(self, note: str) -> None:
        self._notes.append(note)

    @workflow.query
    def get_progress(self) -> OperationProgress:
        return self._progress

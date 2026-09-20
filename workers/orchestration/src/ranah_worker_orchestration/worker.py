"""Worker process entry point: `python -m ranah_worker_orchestration.worker`."""

import asyncio
import logging
import os

from ranah_workflow import TemporalSettings, connect_client
from temporalio.worker import Worker

from ranah_worker_orchestration import activities, discovery_activities, research_activities
from ranah_worker_orchestration.research_workflows import (
    ResearchDiscoveryWorkflow,
    ResearchPlanningWorkflow,
)
from ranah_worker_orchestration.workflows import ResearchFoundationWorkflow

TASK_QUEUE = os.environ.get("RANAH_TASK_QUEUE", "orchestration")


async def run_worker() -> None:
    client = await connect_client(TemporalSettings())
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ResearchFoundationWorkflow, ResearchPlanningWorkflow, ResearchDiscoveryWorkflow],
        activities=[
            activities.create_workflow_run,
            activities.update_workflow_run_status,
            activities.prepare_scope,
            activities.finalize_scope,
            research_activities.generate_research_artifact,
            research_activities.set_operation_stage,
            research_activities.finish_operation,
            discovery_activities.validate_discovery,
            discovery_activities.execute_provider_search,
            discovery_activities.record_provider_failure,
            discovery_activities.normalize_discovery,
            discovery_activities.deduplicate_discovery,
            discovery_activities.verify_discovery,
            discovery_activities.finalize_discovery,
        ],
    )
    logging.info("orchestration worker listening on task queue %r", TASK_QUEUE)
    await worker.run()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

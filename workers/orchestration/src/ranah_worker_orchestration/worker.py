"""Worker process entry point: `python -m ranah_worker_orchestration.worker`."""

import asyncio
import logging

from ranah_workflow import TemporalSettings, connect_client
from temporalio.worker import Worker

from ranah_worker_orchestration import activities
from ranah_worker_orchestration.workflows import ResearchFoundationWorkflow

TASK_QUEUE = "orchestration"


async def run_worker() -> None:
    client = await connect_client(TemporalSettings())
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ResearchFoundationWorkflow],
        activities=[
            activities.create_workflow_run,
            activities.update_workflow_run_status,
            activities.prepare_scope,
            activities.finalize_scope,
        ],
    )
    logging.info("orchestration worker listening on task queue %r", TASK_QUEUE)
    await worker.run()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

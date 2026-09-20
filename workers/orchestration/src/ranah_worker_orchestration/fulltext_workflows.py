from temporalio import workflow
from temporalio.exceptions import ActivityError

from ranah_worker_orchestration.research_workflows import call


@workflow.defn
class FullTextAcquisitionWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "FULL_TEXT_ACQUISITION")
            while batch := await call("prepare_acquisition_batch", operation_id):
                await call("acquire_full_text_batch", operation_id, batch)
                await call("calculate_acquisition_progress", operation_id)
            await call("calculate_acquisition_progress", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            # Assets already stored stay committed; a new operation resumes the rest.
            await call("calculate_acquisition_progress", operation_id)
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"

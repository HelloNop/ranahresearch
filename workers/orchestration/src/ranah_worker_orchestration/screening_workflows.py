from temporalio import workflow
from temporalio.exceptions import ActivityError

from ranah_worker_orchestration.research_workflows import call


@workflow.defn
class ProtocolWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "PROTOCOL_GENERATION")
            await call("generate_protocol", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("finish_operation", operation_id, "FAILED", str(exc.cause or exc))
            return "FAILED"


@workflow.defn
class TitleAbstractScreeningWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "TITLE_ABSTRACT")
            while batch := await call("prepare_screening_batch", operation_id):
                await call("run_screening_batch", operation_id, batch)
                await call("calculate_screening_progress", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("calculate_screening_progress", operation_id)
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"

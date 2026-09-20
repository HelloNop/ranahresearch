from temporalio import workflow
from temporalio.exceptions import ActivityError

from ranah_worker_orchestration.research_workflows import call


@workflow.defn
class FullTextParsingWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "FULL_TEXT_PARSING")
            while batch := await call("prepare_parsing_batch", operation_id):
                await call("parse_assets", operation_id, batch)
                await call("calculate_parsing_progress", operation_id)
            await call("calculate_parsing_progress", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("calculate_parsing_progress", operation_id)
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"

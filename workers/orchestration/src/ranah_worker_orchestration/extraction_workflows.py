from temporalio import workflow
from temporalio.exceptions import ActivityError

from ranah_worker_orchestration.research_workflows import call


@workflow.defn
class EvidenceExtractionWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "EXTRACTION")
            await call("resolve_extraction_corpus", operation_id)
            await call("ensure_extraction_schema", operation_id)
            while batch := await call("prepare_extraction_batch", operation_id):
                await call("extract_evidence_batch", operation_id, batch)
                await call("calculate_extraction_progress", operation_id)
            await call("validate_project_evidence", operation_id)
            await call("review_evidence", operation_id)
            await call("calculate_extraction_progress", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            # Studies already extracted stay persisted; a rerun resumes the rest.
            await call("calculate_extraction_progress", operation_id)
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"

from temporalio import workflow
from temporalio.exceptions import ActivityError

from ranah_worker_orchestration.research_workflows import call


@workflow.defn
class ManuscriptGenerationWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "READINESS")
            await call("validate_manuscript_readiness", operation_id)
            await call("set_operation_stage", operation_id, "SYNTHESIS")
            await call("generate_synthesis", operation_id)
            if kind == "synthesis":
                await call("finish_operation", operation_id, "COMPLETED", None)
                return "COMPLETED"
            await call("set_operation_stage", operation_id, "CLAIMS")
            await call("build_and_verify_claims", operation_id)
            if kind == "claims":
                await call("finish_operation", operation_id, "COMPLETED", None)
                return "COMPLETED"
            await call("set_operation_stage", operation_id, "PLANNING")
            await call("create_manuscript_plan", operation_id)
            if kind == "manuscript_plan":
                await call("finish_operation", operation_id, "COMPLETED", None)
                return "COMPLETED"
            section_ids = await call("prepare_manuscript", operation_id)
            await call("set_operation_stage", operation_id, "WRITING")
            for section_id in section_ids:
                await call("write_manuscript_section", operation_id, section_id)
            await call("complete_manuscript_version", operation_id)
            await call("set_operation_stage", operation_id, "REVIEW")
            await call("run_reviewer_council", operation_id)
            for revision_round in (1, 2):
                revised = await call("revise_open_issues", operation_id, revision_round)
                if not revised:
                    break
                await call("run_reviewer_council", operation_id)
            await call("finalize_manuscript_review", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"


@workflow.defn
class ManuscriptRevisionWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "REVISION")
            await call("revise_open_issues", operation_id, 1)
            await call("set_operation_stage", operation_id, "REVIEW")
            await call("run_reviewer_council", operation_id)
            await call("finalize_manuscript_review", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"


@workflow.defn
class ManuscriptReviewWorkflow:
    @workflow.run
    async def run(self, operation_id: str, kind: str) -> str:
        try:
            await call("set_operation_stage", operation_id, "REVIEW")
            await call("run_reviewer_council", operation_id)
            await call("finalize_manuscript_review", operation_id)
            await call("finish_operation", operation_id, "COMPLETED", None)
            return "COMPLETED"
        except ActivityError as exc:
            await call("finish_operation", operation_id, "PARTIAL", str(exc.cause or exc))
            return "PARTIAL"

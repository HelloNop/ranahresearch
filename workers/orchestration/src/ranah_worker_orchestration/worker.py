"""Worker process entry point: `python -m ranah_worker_orchestration.worker`."""

import asyncio
import logging
import os

from ranah_workflow import TemporalSettings, connect_client
from temporalio.worker import Worker

from ranah_worker_orchestration import (
    activities,
    discovery_activities,
    extraction_activities,
    fulltext_activities,
    fulltext_screening_activities,
    parsing_activities,
    research_activities,
    risk_activities,
    screening_activities,
    study_activities,
    validation_activities,
)
from ranah_worker_orchestration.extraction_workflows import EvidenceExtractionWorkflow
from ranah_worker_orchestration.fulltext_screening_workflows import FullTextScreeningWorkflow
from ranah_worker_orchestration.fulltext_workflows import FullTextAcquisitionWorkflow
from ranah_worker_orchestration.parsing_workflows import FullTextParsingWorkflow
from ranah_worker_orchestration.research_workflows import (
    ResearchDiscoveryWorkflow,
    ResearchPlanningWorkflow,
)
from ranah_worker_orchestration.risk_workflows import RiskOfBiasWorkflow
from ranah_worker_orchestration.screening_workflows import (
    ProtocolWorkflow,
    TitleAbstractScreeningWorkflow,
)
from ranah_worker_orchestration.study_workflows import StudyLinkingWorkflow
from ranah_worker_orchestration.workflows import ResearchFoundationWorkflow

TASK_QUEUE = os.environ.get("RANAH_TASK_QUEUE", "orchestration")


async def run_worker() -> None:
    client = await connect_client(TemporalSettings())
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            ResearchFoundationWorkflow,
            ResearchPlanningWorkflow,
            ResearchDiscoveryWorkflow,
            ProtocolWorkflow,
            TitleAbstractScreeningWorkflow,
            FullTextAcquisitionWorkflow,
            FullTextParsingWorkflow,
            StudyLinkingWorkflow,
            FullTextScreeningWorkflow,
            EvidenceExtractionWorkflow,
            RiskOfBiasWorkflow,
        ],
        activities=[
            fulltext_activities.prepare_acquisition_batch,
            fulltext_activities.acquire_full_text_batch,
            fulltext_activities.calculate_acquisition_progress,
            parsing_activities.prepare_parsing_batch,
            parsing_activities.parse_assets,
            parsing_activities.calculate_parsing_progress,
            fulltext_screening_activities.prepare_full_text_batch,
            fulltext_screening_activities.screen_full_text_batch,
            fulltext_screening_activities.calculate_full_text_progress,
            extraction_activities.resolve_extraction_corpus,
            extraction_activities.ensure_extraction_schema,
            extraction_activities.prepare_extraction_batch,
            extraction_activities.extract_evidence_batch,
            extraction_activities.calculate_extraction_progress,
            validation_activities.validate_project_evidence,
            validation_activities.review_evidence,
            validation_activities.recheck_evidence,
            risk_activities.assess_risk_of_bias,
            study_activities.link_studies,
            study_activities.calculate_study_progress,
            screening_activities.generate_protocol,
            screening_activities.prepare_screening_batch,
            screening_activities.run_screening_batch,
            screening_activities.calculate_screening_progress,
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

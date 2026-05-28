import structlog

from app.core.config import settings
from app.services.ingest import ingest_record
from app.services.matching import match_record
from app.services.routing import route_decision
from app.services.validation import validate_record
from app.services.workflow_engine import (
    get_next_stage,
    increment_retry,
    mark_workflow_complete,
    mark_workflow_failed,
    save_stage_result,
    update_workflow_stage,
)

logger = structlog.get_logger()


def execute_stage(workflow_id: str, stage: str, record_data: dict) -> dict:
    """Execute a single workflow stage and return its result."""
    if stage == "ingestion":
        return ingest_record(workflow_id, record_data)
    elif stage == "matching":
        return match_record(workflow_id, record_data)
    elif stage == "validation":
        return validate_record(workflow_id, record_data)
    elif stage == "decision_routing":
        match_result = record_data.get("_match_result", "OUTSTANDING")
        is_valid = record_data.get("_is_valid", True)
        invoice_total = record_data.get("invoice_total") or 0.0
        return route_decision(workflow_id, match_result, is_valid, invoice_total)
    else:
        raise ValueError(f"Unknown stage: {stage}")


def run_pipeline(workflow_id: str, start_stage: str, record_data: dict):
    """
    Run the workflow pipeline from start_stage to completion.
    Each stage is retried up to MAX_RETRIES on failure.
    """
    stage = start_stage

    while stage:
        update_workflow_stage(workflow_id, stage, "RUNNING")
        success = False

        for attempt in range(1, settings.MAX_RETRIES + 1):
            logger.info(
                "stage_executing", workflow_id=workflow_id, stage=stage, attempt=attempt
            )
            try:
                result = execute_stage(workflow_id, stage, record_data)
                save_stage_result(workflow_id, stage, "SUCCESS", output=result)

                # Enrich record_data with stage outputs for downstream stages
                if stage == "matching":
                    record_data["_match_result"] = result.get("match_result")
                elif stage == "validation":
                    record_data["_is_valid"] = result.get("is_valid")

                logger.info(
                    "stage_success", workflow_id=workflow_id, stage=stage, result=result
                )
                success = True
                break

            except Exception as exc:
                increment_retry(workflow_id)
                save_stage_result(workflow_id, stage, "FAILED", error=str(exc))
                logger.warning(
                    "stage_retrying",
                    workflow_id=workflow_id,
                    stage=stage,
                    attempt=attempt,
                    error=str(exc),
                )

        if not success:
            mark_workflow_failed(
                workflow_id,
                f"Stage '{stage}' failed after {settings.MAX_RETRIES} attempts",
            )
            return

        stage = get_next_stage(stage)

    mark_workflow_complete(workflow_id)



import hashlib
import json
import structlog
import uuid
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.database import get_db_session
from app.schemas.workflow import RecordSubmit
from app.services.failure_sim import maybe_fail
from app.services.workflow_engine import (
    get_next_stage,
    increment_retry,
    mark_workflow_complete,
    mark_workflow_failed,
    save_stage_result,
    update_workflow_stage,
)
from database_ops.model import ARRecord, ProcessedRecord, WorkflowRunStatus, WorkflowStageName, AR_RECONCILIATION_MATCH_STATES
from database_ops.repositories.record_repository import RecordRepository


logger = structlog.get_logger()



class PipelineRunner:
    def __init__(self, workflow_id: str, stage: WorkflowStageName, record_data: RecordSubmit):
        self.workflow_id = workflow_id
        self.stage = stage
        self.record_data = record_data
        self.__validate__()
        logger.info("pipeline_runner_initialized", workflow_id=str(workflow_id), stage=stage.value)

    def __validate__(self):
        if self.validate_uuid(str(self.workflow_id)) is False:
            raise ValueError(f"workflow_id must be UUID, got {type(self.workflow_id)}")
        if not isinstance(self.stage, WorkflowStageName):
            raise ValueError(f"stage must be WorkflowStageName, got {type(self.stage)}")
        if not isinstance(self.record_data, RecordSubmit):
            raise ValueError(f"record_data must be RecordSubmit, got {type(self.record_data)}")
        self.workflow_id = uuid.UUID(str(self.workflow_id))

    @staticmethod
    def validate_uuid(value) -> bool:
        try:
            uuid.UUID(value)
            return True
        except Exception:
            return False

    def run(self):
        """Run the pipeline from start_stage with per-stage retries."""
        try:
            self._execute_pipeline()
        except Exception as exc:
            # Catch all so workflow doesn't stay stuck in RUNNING
            logger.critical(
                "pipeline_unexpected_error",
                workflow_id=str(self.workflow_id),
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            mark_workflow_failed(str(self.workflow_id), f"Unexpected error: {exc}")

    def _execute_stage(self) -> dict:
        """Execute a single workflow stage and return its result."""
        if self.stage == WorkflowStageName.INGESTION:
            return ingest_record(self.workflow_id, self.record_data)
        elif self.stage == WorkflowStageName.MATCHING:
            return match_record(self.workflow_id, self.record_data)
        elif self.stage == WorkflowStageName.VALIDATION:
            return validate_record(self.workflow_id, self.record_data)
        elif self.stage == WorkflowStageName.DECISION_ROUTING:
            match_result = self.record_data._match_result if hasattr(self.record_data, "_match_result") else "OUTSTANDING"
            is_valid = self.record_data._is_valid if hasattr(self.record_data, "_is_valid") else True
            invoice_total = self.record_data.invoice_total or 0.0
            return route_decision(self.workflow_id, match_result, is_valid, invoice_total)
        else:
            raise ValueError(f"Unknown stage: {self.stage}")

    def _execute_pipeline(self):
        """Internal pipeline execution with retry logic per stage."""
        while self.stage:
            update_workflow_stage(str(self.workflow_id), self.stage.value, WorkflowRunStatus.RUNNING)
            success = False

            for attempt in range(1, settings.MAX_RETRIES + 1):
                logger.info(
                    "stage_executing", workflow_id=str(self.workflow_id), stage=self.stage.value, attempt=attempt
                )
                try:
                    result = self._execute_stage()
                    save_stage_result(str(self.workflow_id), self.record_data.customer_id, self.stage.value, "SUCCESS", output=result)

                    # Enrich record_data with stage outputs for downstream stages
                    if self.stage == WorkflowStageName.MATCHING:
                        self.record_data._match_result = result.get("match_result")
                    elif self.stage == WorkflowStageName.VALIDATION:
                        self.record_data._is_valid = result.get("is_valid")

                    logger.info(
                        "stage_success", workflow_id=str(self.workflow_id), stage=self.stage.value, result=result
                    )
                    success = True
                    break

                except Exception as exc:
                    increment_retry(str(self.workflow_id))
                    save_stage_result(str(self.workflow_id), self.record_data.customer_id, self.stage.value, "FAILED", error=str(exc))
                    logger.warning(
                        "stage_retrying",
                        workflow_id=str(self.workflow_id),
                        stage=self.stage.value,
                        attempt=attempt,
                        error=str(exc),
                    )

            if not success:
                mark_workflow_failed(
                    str(self.workflow_id),
                    f"Stage '{self.stage.value}' failed after {settings.MAX_RETRIES} attempts",
                )
                return

            self.stage = get_next_stage(self.stage)

        mark_workflow_complete(str(self.workflow_id))


# Pipeline stages
def ingest_record(workflow_id: str, record_data: RecordSubmit) -> dict:
    """Parse and persist the raw AR record with idempotency check."""
    if settings.ENVIRONMENT != 'prod':
        maybe_fail()

    customer_id = record_data.customer_id
    # Use model_dump() to get a dict representation for hashing
    record_dict = record_data.model_dump() if hasattr(record_data, "model_dump") else record_data.dict()
    idempotency_key = hashlib.sha256(
        json.dumps(record_dict, sort_keys=True).encode()
    ).hexdigest()

    with get_db_session() as db:
        repo = RecordRepository(db)
        # Check for duplicate
        existing = repo.get_processed_record_by_idempotency_key(idempotency_key)
        if existing:
            logger.info(
                "duplicate_record_skipped",
                customer_id=customer_id,
                workflow_id=workflow_id,
            )
            return {"status": "DUPLICATE", "record_id": existing.id}

        record_id = str(uuid.uuid4())
        ar_record = ARRecord(
            id=record_id,
            customer_id=customer_id,
            customer_balance=record_data.customer_balance,
            invoice_total=record_data.invoice_total,
            invoice_applied_amount=record_data.invoice_applied_amount,
            invoice_exchange_rate=record_data.invoice_exchange_rate,
            payment_total=record_data.payment_total,
            payment_applied_amount=record_data.payment_applied_amount,
            payment_exchange_rate=record_data.payment_exchange_rate,
            credit_total=record_data.credit_total,
            credit_applied_amount=record_data.credit_applied_amount,
            credit_exchange_rate=record_data.credit_exchange_rate,
            adjustment_total=record_data.adjustment_total,
            adjustment_applied_amount=record_data.adjustment_applied_amount,
            adjustment_exchange_rate=record_data.adjustment_exchange_rate,
        )
        processed = ProcessedRecord(
            idempotency_key=idempotency_key,
            customer_id=customer_id,
        )
        try:
            repo.insert_ar_record_and_processed(ar_record, processed)
        except ValueError as ve:
            logger.error(
                "record_validation_error",
                customer_id=customer_id,
                workflow_id=workflow_id,
                error=str(ve),
            )
            return {"status": "ERROR", "error": str(ve)}
        except IntegrityError:
            existing = repo.get_processed_record_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(
                    "duplicate_record_concurrent",
                    customer_id=customer_id,
                    workflow_id=workflow_id,
                )
                return {"status": "DUPLICATE", "record_id": existing.customer_id}
            raise

        logger.info("record_ingested", record_id=record_id, workflow_id=workflow_id)
        return {"status": "INGESTED", "record_id": record_id, "workflow_id": workflow_id}


def match_record(workflow_id: str, record_data: RecordSubmit) -> dict:
    """Compare invoice vs payment totals and classify as MATCHED/OUTSTANDING/PARTIAL/OVERPAID."""
    if settings.ENVIRONMENT != 'prod':
        maybe_fail()

    invoice_total = record_data.invoice_total or 0.0
    payment_total = record_data.payment_total or 0.0

    # Percentage-based tolerance (e.g. 5% means within 5% of invoice is considered matched)
    tolerance = (
        (settings.MATCH_TOLERANCE_PERCENT / 100.0) * invoice_total
        if invoice_total
        else 0.01
    )

    if abs(payment_total - invoice_total) <= tolerance:
        match_result = AR_RECONCILIATION_MATCH_STATES.MATCHED.value
    elif payment_total == 0:
        match_result = AR_RECONCILIATION_MATCH_STATES.OUTSTANDING.value
    elif payment_total < invoice_total:
        match_result = AR_RECONCILIATION_MATCH_STATES.PARTIAL.value
    else:
        match_result = AR_RECONCILIATION_MATCH_STATES.OVERPAID.value

    logger.info(
        "matching_complete",
        workflow_id=workflow_id,
        match_result=match_result,
        invoice_total=invoice_total,
        payment_total=payment_total,
    )

    return {
        "match_result": match_result,
        "invoice_total": invoice_total,
        "payment_total": payment_total,
        "difference": round(payment_total - invoice_total, 2),
    }


def validate_record(workflow_id: str, record_data: RecordSubmit) -> dict:
    """Apply business rule checks (required fields, non-negative amounts, valid rates)."""
    if settings.ENVIRONMENT != 'prod':
        maybe_fail()

    errors = []

    if not record_data.customer_id:
        errors.append("Missing customer_id")

    invoice_total = record_data.invoice_total
    if invoice_total is not None and invoice_total < 0:
        errors.append("Negative invoice_total")

    payment_total = record_data.payment_total
    if payment_total is not None and payment_total < 0:
        errors.append("Negative payment_total")

    for rate_field in [
        "invoice_exchange_rate",
        "payment_exchange_rate",
        "credit_exchange_rate",
        "adjustment_exchange_rate",
    ]:
        rate = getattr(record_data, rate_field)
        if rate is not None and rate <= 0:
            errors.append(f"Invalid {rate_field}: {rate}")

    is_valid = len(errors) == 0

    logger.info(
        "validation_complete",
        workflow_id=workflow_id,
        is_valid=is_valid,
        error_count=len(errors),
    )

    return {
        "is_valid": is_valid,
        "errors": errors,
    }


def route_decision(
    workflow_id: str, match_result: str, is_valid: bool, invoice_total: float = 0.0
) -> dict:
    """
    Decision routing stage: determine final disposition based on matching + validation.

    If validation failed, route to REJECTED.
    Otherwise, route based on match result.
    High-value invoices are flagged for priority review.
    """
    if settings.ENVIRONMENT != 'prod':
        maybe_fail()

    high_value = invoice_total >= settings.HIGH_VALUE_THRESHOLD

    if not is_valid:
        decision = "REJECTED"
    elif high_value and match_result != "MATCHED":
        decision = "FINANCE_REVIEW"
    else:
        decision = settings.AR_RECONCILIATION_PIPELINE_ROUTING_TABLE.get(match_result, "MANUAL_REVIEW")

    logger.info(
        "routing_complete",
        workflow_id=workflow_id,
        decision=decision,
        match_result=match_result,
        is_valid=is_valid,
        high_value=high_value,
    )

    return {
        "decision": decision,
        "match_result": match_result,
        "is_valid": is_valid,
        "high_value": high_value,
    }

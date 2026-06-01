import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from database_ops.models import ProcessedRecord, ReconciliationVerdict
from database_ops.repositories.processed_record_repository import (
    ProcessedRecordRepository,
)

logger = structlog.get_logger()


class ProcessedRecordService:
    """Service for managing processed reconciliation records."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = ProcessedRecordRepository(db)

    def create_from_pipeline_output(
        self,
        customer_id: str,
        workflow_id: str,
        pipeline_output: dict[str, Any],
        processing_started_at: datetime | None = None,
    ) -> ProcessedRecord:
        """
        Create a ProcessedRecord from pipeline output.

        Args:
            customer_id: The customer ID
            workflow_id: The workflow run ID
            pipeline_output: The final output from the reporting stage
            processing_started_at: When the pipeline started processing

        Returns:
            The created ProcessedRecord
        """
        # Check if record already exists for this workflow
        existing = self.repo.get_by_workflow_id(workflow_id)
        if existing:
            logger.info(
                "processed_record_already_exists",
                workflow_id=workflow_id,
                customer_id=customer_id,
            )
            return existing

        # Extract verdict data from reconciliation_verdict (first/only record)
        verdicts = pipeline_output.get("reconciliation_verdict", [])
        verdict_data = verdicts[0] if verdicts else {}

        # Parse verdict enum
        verdict_str = verdict_data.get("verdict", "MANUAL_REVIEW")
        if isinstance(verdict_str, str):
            try:
                verdict_enum = ReconciliationVerdict[verdict_str.upper()]
            except KeyError:
                verdict_enum = ReconciliationVerdict.MANUAL_REVIEW
        else:
            verdict_enum = ReconciliationVerdict.MANUAL_REVIEW

        # Calculate processing time
        processing_completed_at = datetime.now(UTC)
        total_processing_time_ms = None
        if processing_started_at:
            delta = processing_completed_at - processing_started_at
            total_processing_time_ms = int(delta.total_seconds() * 1000)

        # Serialize reports to JSON
        summary_report_json = self._safe_json_dumps(
            pipeline_output.get("summary_report")
        )
        exception_report_json = self._safe_json_dumps(
            pipeline_output.get("exception_report")
        )
        audit_report_json = self._safe_json_dumps(pipeline_output.get("audit_report"))
        triggered_rules_json = self._safe_json_dumps(
            verdict_data.get("triggered_rules_summary", [])
        )

        processed_record = ProcessedRecord(
            customer_id=customer_id,
            workflow_id=workflow_id,
            verdict=verdict_enum,
            confidence=verdict_data.get("confidence", 0),
            reason=verdict_data.get("reason"),
            customer_balance=verdict_data.get("customer_balance"),
            expected_balance=verdict_data.get("expected_balance"),
            difference=verdict_data.get("difference"),
            invoice_outstanding=verdict_data.get("invoice_outstanding"),
            payment_unapplied=verdict_data.get("payment_unapplied"),
            credit_available=verdict_data.get("credit_available"),
            adjustment_remaining=verdict_data.get("adjustment_remaining"),
            triggered_rules=triggered_rules_json,
            summary_report=summary_report_json,
            exception_report=exception_report_json,
            audit_report=audit_report_json,
            processing_started_at=processing_started_at,
            processing_completed_at=processing_completed_at,
            total_processing_time_ms=total_processing_time_ms,
        )

        created = self.repo.create(processed_record)

        logger.info(
            "processed_record_created",
            workflow_id=workflow_id,
            customer_id=customer_id,
            verdict=verdict_enum.value,
            confidence=verdict_data.get("confidence", 0),
            processing_time_ms=total_processing_time_ms,
        )

        return created

    def _safe_json_dumps(self, data: Any) -> str | None:
        """Safely serialize data to JSON string."""
        if data is None:
            return None
        try:
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            logger.error("json_serialization_failed", error=str(e))
            return None

    def get_by_id(self, record_id: str) -> ProcessedRecord | None:
        """Get a processed record by ID."""
        return self.repo.get_by_id(record_id)

    def get_by_workflow_id(self, workflow_id: str) -> ProcessedRecord | None:
        """Get a processed record by workflow ID."""
        return self.repo.get_by_workflow_id(workflow_id)

    def get_by_customer_id(self, customer_id: str) -> ProcessedRecord | None:
        """Get the most recent processed record for a customer."""
        return self.repo.get_by_customer_id(customer_id)

    def get_all(self) -> list[ProcessedRecord]:
        """Get all processed records."""
        return self.repo.get_all()

    def get_by_verdict(self, verdict: str) -> list[ProcessedRecord]:
        """Get all processed records with a specific verdict."""
        return self.repo.get_by_verdict(verdict)

    def exists_for_workflow(self, workflow_id: str) -> bool:
        """Check if a processed record exists for a workflow."""
        return self.repo.exists_by_workflow_id(workflow_id)

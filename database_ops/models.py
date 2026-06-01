import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Enum as SQLEnum

from app.core.database import Base


# Workflow models
class WorkflowRunStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"


class WorkflowStageName(Enum):
    INGESTION = "INGESTION"
    NORMALIZATION = "NORMALIZATION"
    BALANCE_COMPUTE = "BALANCE_COMPUTE"
    RECONCILIATION = "RECONCILIATION"
    VALIDATION_RULES = "VALIDATION_RULES"
    VERDICT_GENERATION = "VERDICT_GENERATION"
    REPORTING = "REPORTING"


class ARReconciliationMatchStates(Enum):
    MATCHED = "MATCHED"
    OUTSTANDING = "OUTSTANDING"
    PARTIAL = "PARTIAL"
    OVERPAID = "OVERPAID"


class ARRecord(Base):
    __tablename__ = "ar_records"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    customer_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("customers.id"), nullable=False, unique=True
    )
    customer_balance: Mapped[float | None] = mapped_column(Float, nullable=True)

    invoice_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoice_applied_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoice_exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    payment_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_applied_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    credit_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    credit_applied_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    credit_exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    adjustment_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjustment_applied_amount: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    adjustment_exchange_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # id: Mapped[uuid.UUID] = mapped_column(
    #     String, primary_key=True, default=uuid.uuid4
    # )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("customers.id"), nullable=False, unique=True
    )
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLEnum(WorkflowRunStatus, name="workflow_run_status"),
        nullable=False,
        default=WorkflowRunStatus.PENDING,
    )
    current_stage: Mapped[WorkflowStageName | None] = mapped_column(
        SQLEnum(WorkflowStageName, name="workflow_stage_name"),
        nullable=False,
        default=WorkflowStageName.INGESTION,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class WorkflowStageState(Base):
    __tablename__ = "workflow_stage_state"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    stage_name: Mapped[WorkflowStageName | None] = mapped_column(
        SQLEnum(WorkflowStageName, name="workflow_stage_name"),
        nullable=False,
        default=WorkflowStageName.INGESTION,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLEnum(WorkflowRunStatus, name="workflow_run_status"),
        nullable=False,
        default=WorkflowRunStatus.PENDING,
    )
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ReconciliationVerdict(Enum):
    """Final verdict from the reconciliation pipeline."""

    MATCH = "MATCH"
    OVERPAID = "OVERPAID"
    UNDERPAID = "UNDERPAID"
    UNAPPLIED_PAYMENT = "UNAPPLIED_PAYMENT"
    UNAPPLIED_CREDIT = "UNAPPLIED_CREDIT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ProcessedRecord(Base):
    """Stores the final output of the AR reconciliation pipeline."""

    __tablename__ = "processed_records"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str] = mapped_column(
        String, ForeignKey("customers.id"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id"), nullable=False, unique=True, index=True
    )

    # Verdict information
    verdict: Mapped[ReconciliationVerdict] = mapped_column(
        SQLEnum(ReconciliationVerdict, name="reconciliation_verdict"),
        nullable=False,
    )
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)

    # Balance snapshot at processing time
    customer_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    difference: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Breakdown amounts
    invoice_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_unapplied: Mapped[float | None] = mapped_column(Float, nullable=True)
    credit_available: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjustment_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Triggered rules as JSON array
    triggered_rules: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full reports as JSON
    summary_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Processing metadata
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    total_processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

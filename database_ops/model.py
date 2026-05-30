import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SQLEnum

from app.core.database import Base



# Workflow models
class WorkflowRunStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"

class WorkflowStageName(Enum):
    INGESTION = "ingestion"
    MATCHING = "matching"
    VALIDATION = "validation"
    DECISION_ROUTING = "decision_routing"


class AR_RECONCILIATION_MATCH_STATES(Enum):
    MATCHED = "MATCHED"
    OUTSTANDING = "OUTSTANDING"
    PARTIAL = "PARTIAL"
    OVERPAID = "OVERPAID"

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
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=False, unique=True)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLEnum(WorkflowRunStatus, name="workflow_run_status"),
        nullable=False,
        default=WorkflowRunStatus.PENDING,
    )
    current_stage: Mapped[WorkflowStageName | None] = mapped_column(SQLEnum(WorkflowStageName, name="workflow_stage_name"), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    stages: Mapped[list["WorkflowStageState"]] = relationship(
        "WorkflowStageState", back_populates="workflow", cascade="all, delete-orphan"
    )
    raw_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=False
    )


class WorkflowStageState(Base):
    __tablename__ = "workflow_stage_state"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id"), nullable=False, index=True
    )
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLEnum(WorkflowRunStatus, name="workflow_run_status"),
        nullable=False,
        default=WorkflowRunStatus.PENDING,
    )
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    workflow: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="stages"
    )


class ARRecord(Base):
    __tablename__ = "ar_records"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=False, unique=True)
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


class ProcessedRecord(Base):
    __tablename__ = "processed_records"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[str | None] = mapped_column(String, ForeignKey("customers.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

import csv
import io

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.workflow import (
    BulkUploadResponse,
    RecordSubmit,
    SubmitResponse,
)
from app.services.pipeline import run_pipeline
from app.services.workflow_engine import (
    check_duplicate_submission,
    create_workflow,
    reset_workflow,
)

logger = structlog.get_logger()

router = APIRouter(tags=["submissions"])


def _safe_float(value: str | None) -> float | None:
    """Safely parse a float from a CSV value, returning None on failure."""
    if not value or not value.strip():
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@router.post("/submit", response_model=SubmitResponse, status_code=201)
def submit_record(
    record: RecordSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submit a single AR record for processing.
    Idempotent: duplicate submissions return the existing workflow ID.
    """
    existing = check_duplicate_submission(db, record.customer_id)
    if existing:
        return SubmitResponse(
            workflow_id=existing.id,
            status=existing.status,
            message="Duplicate submission — returning existing workflow",
        )

    record_data = record.model_dump()
    workflow = create_workflow(db, record.customer_id, record_data)

    background_tasks.add_task(run_pipeline, workflow.id, "ingestion", record_data)

    return SubmitResponse(
        workflow_id=workflow.id,
        status="PENDING",
        message="Workflow created and queued for processing",
    )


@router.put("/submit/{customer_id}", response_model=SubmitResponse)
def update_record(
    customer_id: str,
    record: RecordSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Update an existing AR record and reprocess the workflow from scratch.
    If no existing record, creates a new one.
    """
    existing = check_duplicate_submission(db, customer_id)
    if not existing:
        record_data = record.model_dump()
        workflow = create_workflow(db, record.customer_id, record_data)
        background_tasks.add_task(run_pipeline, workflow.id, "ingestion", record_data)
        return SubmitResponse(
            workflow_id=workflow.id,
            status="PENDING",
            message="No existing record found — created new workflow",
        )

    record_data = record.model_dump()
    reset_workflow(db, existing.id)
    background_tasks.add_task(run_pipeline, existing.id, "ingestion", record_data)

    return SubmitResponse(
        workflow_id=existing.id,
        status="PENDING",
        message="Record updated — workflow reprocessing from start",
    )


@router.post("/bulk-upload", response_model=BulkUploadResponse, status_code=201)
async def bulk_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a CSV file for bulk AR reconciliation.
    Each row becomes a separate workflow processed in parallel.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    workflow_ids = []
    duplicates = 0
    submitted = 0

    for row in reader:
        record_data = {
            "customer_id": row.get("Customer ID", ""),
            "customer_name": row.get("Customer Name"),
            "customer_balance": _safe_float(row.get("Customer Balance")),
            "invoice_total": _safe_float(row.get("Invoice Total")),
            "invoice_applied_amount": _safe_float(row.get("Invoice applied amount")),
            "invoice_exchange_rate": _safe_float(row.get("Invoice exchange rate")),
            "payment_total": _safe_float(row.get("Payment Total")),
            "payment_applied_amount": _safe_float(row.get("Payment applied amount")),
            "payment_exchange_rate": _safe_float(row.get("Payment exchange rate")),
            "credit_total": _safe_float(row.get("Credit Total")),
            "credit_applied_amount": _safe_float(row.get("Credit applied amount")),
            "credit_exchange_rate": _safe_float(row.get("Credit exchange rate")),
            "adjustment_total": _safe_float(row.get("Adjustment Total")),
            "adjustment_applied_amount": _safe_float(
                row.get("Adjustment applied amount")
            ),
            "adjustment_exchange_rate": _safe_float(
                row.get("Adjustment exchange rate")
            ),
        }

        customer_id = record_data["customer_id"]
        if not customer_id:
            continue

        existing = check_duplicate_submission(db, customer_id)
        if existing:
            duplicates += 1
            workflow_ids.append(existing.id)
            continue

        workflow = create_workflow(db, customer_id, record_data)
        background_tasks.add_task(run_pipeline, workflow.id, "ingestion", record_data)
        workflow_ids.append(workflow.id)
        submitted += 1

    return BulkUploadResponse(
        total_records=submitted + duplicates,
        submitted=submitted,
        duplicates=duplicates,
        workflow_ids=workflow_ids,
    )

import csv
import io
from datetime import UTC, datetime

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.ar_reconciliation import (
    RecordSubmitRequest,
    RecordSubmitResponse,
)
from app.services.ar_reconciliation_pipeline.pipeline_runner import PipelineRunner
from database_ops.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStageName,
    WorkflowStageState,
)
from database_ops.services.ar_record_service import ARRecordService
from database_ops.services.customer_service import CustomerService
from database_ops.services.workflow_run_service import WorkflowRunService
from database_ops.services.workflow_stage_state_service import WorkflowStageStateService

logger = structlog.get_logger()

router = APIRouter(tags=["ar_reconciliation_records"])


def build_duplicate_response(
    customer_id: str,
    workflow,
) -> RecordSubmitResponse:
    """
    Build a response for an already existing workflow.
    """

    if workflow is None:
        raise ValueError(f"Workflow not found for customer_id={customer_id}")

    return RecordSubmitResponse(
        customer_id=str(customer_id),
        workflow_id=str(workflow.id),
        workflow_status=workflow.status.value,
        workflow_current_stage=workflow.current_stage.value,
        message=(
            "Duplicate submission detected. "
            "Returning existing workflow details. "
            "Use the update endpoint to modify customer data."
        ),
    )


@router.post(
    "/submit",
    response_model=RecordSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_record(
    record: RecordSubmitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submit an AR record.

    Behaviour:
    - Idempotent by customer_id.
    - Duplicate requests return existing workflow.
    - Handles concurrent submissions safely.
    """

    customer_id = record.customer_id

    ar_record_service = ARRecordService(db)
    customer_service = CustomerService(db)
    workflow_service = WorkflowRunService(db)

    try:
        existing_workflow = workflow_service.get_workflow_by_customer_id(customer_id)

        if existing_workflow:
            logger.info(
                "duplicate_submission_detected",
                customer_id=customer_id,
                workflow_id=str(existing_workflow.id),
                workflow_status=existing_workflow.status.value,
            )

            return build_duplicate_response(
                customer_id,
                existing_workflow,
            )

        if not customer_service.customer_exists(customer_id):
            customer_service.create_customer(
                customer_id=customer_id,
                customer_name=record.customer_name,
            )

        ar_record_service.create_record(
            customer_id=customer_id,
            customer_balance=record.customer_balance,
            invoice_total=record.invoice_total,
            invoice_applied_amount=record.invoice_applied_amount,
            invoice_exchange_rate=record.invoice_exchange_rate,
            payment_total=record.payment_total,
            payment_applied_amount=record.payment_applied_amount,
            payment_exchange_rate=record.payment_exchange_rate,
            credit_total=record.credit_total,
            credit_applied_amount=record.credit_applied_amount,
            credit_exchange_rate=record.credit_exchange_rate,
            adjustment_total=record.adjustment_total,
            adjustment_applied_amount=record.adjustment_applied_amount,
            adjustment_exchange_rate=record.adjustment_exchange_rate,
        )

        workflow = workflow_service.create_workflow(customer_id=customer_id)

        # Create initial workflow_stage_state record for INGESTION stage
        workflow_stage_state_service = WorkflowStageStateService(db)
        workflow_stage_state_service.create_stage_state(
            workflow_id=workflow.id,
            stage_name=WorkflowStageName.INGESTION,
            status=WorkflowRunStatus.PENDING,
        )

        db.commit()
        db.refresh(workflow)

        logger.info(
            "record_submitted",
            customer_id=customer_id,
            workflow_id=str(workflow.id),
        )

        background_tasks.add_task(PipelineRunner(workflow.id, customer_id).run)

        return RecordSubmitResponse(
            customer_id=str(customer_id),
            workflow_id=str(workflow.id),
            workflow_status=workflow.status.value,
            workflow_current_stage=workflow.current_stage.value,
            message="Record submitted successfully.",
        )

    except IntegrityError:
        db.rollback()

        logger.warning(
            "duplicate_submission_race_condition",
            customer_id=customer_id,
        )

        existing_workflow = workflow_service.get_workflow_by_customer_id(customer_id)

        if existing_workflow:
            return build_duplicate_response(
                customer_id,
                existing_workflow,
            )

        raise


# CSV column mapping for bulk upload
CSV_COLUMN_MAP = {
    "Customer ID": "customer_id",
    "Customer Name": "customer_name",
    "Customer Balance": "customer_balance",
    "Invoice Total": "invoice_total",
    "Invoice applied amount": "invoice_applied_amount",
    "Invoice exchange rate": "invoice_exchange_rate",
    "Payment Total": "payment_total",
    "Payment applied amount": "payment_applied_amount",
    "Payment exchange rate": "payment_exchange_rate",
    "Credit Total": "credit_total",
    "Credit applied amount": "credit_applied_amount",
    "Credit exchange rate": "credit_exchange_rate",
    "Adjustment Total": "adjustment_total",
    "Adjustment applied amount": "adjustment_applied_amount",
    "Adjustment exchange rate": "adjustment_exchange_rate",
}


def _parse_float(value: str) -> float:
    """Safely parse float from string, return 0.0 on failure."""
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0


@router.post("/bulk-upload", status_code=status.HTTP_200_OK)
async def bulk_upload(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """
    Upload a CSV file to process multiple AR records at once.
    Each row becomes an independent workflow processed in parallel.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file",
        )

    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    workflow_ids = []
    duplicates = 0
    submitted = 0
    errors = []

    ar_record_service = ARRecordService(db)
    customer_service = CustomerService(db)
    workflow_service = WorkflowRunService(db)
    workflow_stage_state_service = WorkflowStageStateService(db)

    for row_num, row in enumerate(reader, start=2):
        try:
            customer_id = row.get("Customer ID", "").strip()
            if not customer_id:
                errors.append({"row": row_num, "error": "Missing Customer ID"})
                continue

            # Check for existing workflow
            existing_workflow = workflow_service.get_workflow_by_customer_id(
                customer_id
            )
            if existing_workflow:
                duplicates += 1
                workflow_ids.append(str(existing_workflow.id))
                continue

            # Create customer if not exists
            if not customer_service.customer_exists(customer_id):
                customer_service.create_customer(
                    customer_id=customer_id,
                    customer_name=row.get("Customer Name", f"Customer {customer_id}"),
                )

            # Create AR record
            ar_record_service.create_record(
                customer_id=customer_id,
                customer_balance=_parse_float(row.get("Customer Balance")),
                invoice_total=_parse_float(row.get("Invoice Total")),
                invoice_applied_amount=_parse_float(row.get("Invoice applied amount")),
                invoice_exchange_rate=_parse_float(row.get("Invoice exchange rate"))
                or 1.0,
                payment_total=_parse_float(row.get("Payment Total")),
                payment_applied_amount=_parse_float(row.get("Payment applied amount")),
                payment_exchange_rate=_parse_float(row.get("Payment exchange rate"))
                or 1.0,
                credit_total=_parse_float(row.get("Credit Total")),
                credit_applied_amount=_parse_float(row.get("Credit applied amount")),
                credit_exchange_rate=_parse_float(row.get("Credit exchange rate"))
                or 1.0,
                adjustment_total=_parse_float(row.get("Adjustment Total")),
                adjustment_applied_amount=_parse_float(
                    row.get("Adjustment applied amount")
                ),
                adjustment_exchange_rate=_parse_float(
                    row.get("Adjustment exchange rate")
                )
                or 1.0,
            )

            # Create workflow
            workflow = workflow_service.create_workflow(customer_id=customer_id)
            workflow_stage_state_service.create_stage_state(
                workflow_id=workflow.id,
                stage_name=WorkflowStageName.INGESTION,
                status=WorkflowRunStatus.PENDING,
            )

            db.commit()
            db.refresh(workflow)

            workflow_ids.append(str(workflow.id))
            submitted += 1

            # Queue background task for pipeline execution
            if background_tasks:
                background_tasks.add_task(PipelineRunner(workflow.id, customer_id).run)

            logger.info(
                "bulk_record_submitted",
                customer_id=customer_id,
                workflow_id=str(workflow.id),
            )

        except Exception as e:
            db.rollback()
            errors.append({"row": row_num, "error": str(e)})
            logger.error("bulk_upload_row_error", row=row_num, error=str(e))

    return {
        "total_records": submitted + duplicates + len(errors),
        "submitted": submitted,
        "duplicates": duplicates,
        "errors": len(errors),
        "error_details": errors[:10],  # Limit error details
        "workflow_ids": workflow_ids,
    }


@router.get("/workflow/{workflow_id}")
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
):
    """
    Get workflow status and all stage details.
    """
    workflow = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )

    stages = (
        db.query(WorkflowStageState)
        .filter(WorkflowStageState.workflow_id == workflow_id)
        .order_by(WorkflowStageState.created_at)
        .all()
    )

    return {
        "workflow": {
            "id": str(workflow.id),
            "customer_id": workflow.customer_id,
            "status": workflow.status.value,
            "current_stage": workflow.current_stage.value
            if workflow.current_stage
            else None,
            "retry_count": workflow.retry_count,
            "created_at": workflow.created_at.isoformat()
            if workflow.created_at
            else None,
            "updated_at": workflow.updated_at.isoformat()
            if workflow.updated_at
            else None,
        },
        "stages": [
            {
                "id": str(stage.id),
                "stage_name": stage.stage_name.value if stage.stage_name else None,
                "status": stage.status.value,
                "retry_count": stage.retry_count,
                "error_message": stage.error_message,
                "created_at": stage.created_at.isoformat()
                if stage.created_at
                else None,
                "updated_at": stage.updated_at.isoformat()
                if stage.updated_at
                else None,
            }
            for stage in stages
        ],
    }


@router.get("/workflows")
def list_workflows(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List all workflows with optional status filter and pagination.
    """
    query = db.query(WorkflowRun)

    if status_filter:
        try:
            status_enum = WorkflowRunStatus[status_filter.upper()]
            query = query.filter(WorkflowRun.status == status_enum)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Valid: {[s.name for s in WorkflowRunStatus]}",
            ) from None

    workflows = (
        query.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()
    )

    return [
        {
            "id": str(w.id),
            "customer_id": w.customer_id,
            "status": w.status.value,
            "current_stage": w.current_stage.value if w.current_stage else None,
            "retry_count": w.retry_count,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
        }
        for w in workflows
    ]


@router.get("/workflows/enhanced")
def list_workflows_enhanced(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    stale_minutes: int = Query(10, ge=1),
    db: Session = Depends(get_db),
):
    """
    Enhanced workflow listing with staleness detection and last error message.
    """
    query = db.query(WorkflowRun)

    if status_filter:
        try:
            status_enum = WorkflowRunStatus[status_filter.upper()]
            query = query.filter(WorkflowRun.status == status_enum)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            ) from None

    workflows = query.order_by(WorkflowRun.created_at.desc()).limit(limit).all()
    now = datetime.now(UTC)

    results = []
    for w in workflows:
        # Check for staleness (stuck in RUNNING for too long)
        is_stale = False
        if w.status == WorkflowRunStatus.RUNNING and w.updated_at:
            age_minutes = (now - w.updated_at.replace(tzinfo=UTC)).total_seconds() / 60
            is_stale = age_minutes > stale_minutes

        # Get last error from stage states
        last_error = None
        if w.status == WorkflowRunStatus.FAILED:
            stage = (
                db.query(WorkflowStageState)
                .filter(
                    WorkflowStageState.workflow_id == w.id,
                    WorkflowStageState.error_message.isnot(None),
                )
                .order_by(WorkflowStageState.updated_at.desc())
                .first()
            )
            if stage:
                last_error = stage.error_message

        results.append(
            {
                "id": str(w.id),
                "customer_id": w.customer_id,
                "status": w.status.value,
                "current_stage": w.current_stage.value if w.current_stage else None,
                "retry_count": w.retry_count,
                "is_stale": is_stale,
                "last_error": last_error,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
            }
        )

    return results


@router.post("/resume/{workflow_id}")
def resume_workflow(
    workflow_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Resume a failed workflow from the last successful stage.
    """
    workflow = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )

    if workflow.status not in {WorkflowRunStatus.FAILED, WorkflowRunStatus.RETRYING}:
        return {
            "workflow_id": str(workflow.id),
            "status": workflow.status.value,
            "message": f"Workflow is {workflow.status.value}, not eligible for resume. Only FAILED workflows can be resumed.",
        }

    # Reset status to RUNNING
    workflow.status = WorkflowRunStatus.RUNNING
    db.commit()
    db.refresh(workflow)

    # Resume from current stage (the failed one)
    resume_stage = workflow.current_stage
    customer_id = workflow.customer_id

    logger.info(
        "workflow_resuming",
        workflow_id=str(workflow.id),
        resume_stage=resume_stage.value if resume_stage else "INGESTION",
    )

    # Queue pipeline execution from the failed stage
    background_tasks.add_task(
        PipelineRunner(
            workflow_id=str(workflow.id),
            customer_id=customer_id,
            stage=resume_stage,
        ).run
    )

    return {
        "workflow_id": str(workflow.id),
        "status": "RESUMING",
        "resume_stage": resume_stage.value if resume_stage else "INGESTION",
        "message": "Workflow is being resumed from the last failed stage.",
    }


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """
    Get aggregate statistics about all workflows.
    """
    total = db.query(WorkflowRun).count()
    completed = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == WorkflowRunStatus.COMPLETED)
        .count()
    )
    failed = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == WorkflowRunStatus.FAILED)
        .count()
    )
    pending = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == WorkflowRunStatus.PENDING)
        .count()
    )
    running = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == WorkflowRunStatus.RUNNING)
        .count()
    )
    retrying = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == WorkflowRunStatus.RETRYING)
        .count()
    )

    # Count stale workflows (stuck in RUNNING for > 10 minutes)
    now = datetime.now(UTC)
    all_running = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status == WorkflowRunStatus.RUNNING)
        .all()
    )
    stale = sum(
        1
        for w in all_running
        if w.updated_at
        and (now - w.updated_at.replace(tzinfo=UTC)).total_seconds() > 600
    )

    # Get verdict distribution from completed workflows
    decisions = {"matched": 0, "overpaid": 0, "underpaid": 0, "manual_review": 0}
    # Note: Full verdict tracking would require storing verdicts in the database

    return {
        "total_workflows": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "running": running,
        "retrying": retrying,
        "stale": stale,
        "decisions": decisions,
        "completion_rate": round(completed / total * 100, 2) if total > 0 else 0,
        "failure_rate": round(failed / total * 100, 2) if total > 0 else 0,
    }


@router.get("/export")
def export_results(
    status_filter: str | None = Query("COMPLETED", alias="status"),
    db: Session = Depends(get_db),
):
    """
    Export workflow results as CSV.
    """
    query = db.query(WorkflowRun)

    if status_filter:
        try:
            status_enum = WorkflowRunStatus[status_filter.upper()]
            query = query.filter(WorkflowRun.status == status_enum)
        except KeyError:
            pass

    workflows = query.order_by(WorkflowRun.created_at.desc()).all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "workflow_id",
            "customer_id",
            "status",
            "current_stage",
            "retry_count",
            "created_at",
            "updated_at",
        ]
    )

    for w in workflows:
        writer.writerow(
            [
                str(w.id),
                w.customer_id,
                w.status.value,
                w.current_stage.value if w.current_stage else "",
                w.retry_count,
                w.created_at.isoformat() if w.created_at else "",
                w.updated_at.isoformat() if w.updated_at else "",
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=workflow_results.csv"},
    )

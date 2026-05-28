import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.models.workflow import WorkflowRun, WorkflowStageState

logger = structlog.get_logger()

STAGES = [
    "ingestion",
    "matching",
    "validation",
    "decision_routing",
]


def get_next_stage(current: str | None) -> str | None:
    """Return the next stage in the pipeline, or None if complete."""
    if current is None:
        return STAGES[0]
    try:
        idx = STAGES.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(STAGES):
        return None
    return STAGES[idx + 1]


def create_workflow(db: Session, customer_id: str, record_data: dict) -> WorkflowRun:
    """Create a new workflow run. Returns existing if concurrent duplicate."""
    workflow_id = str(uuid.uuid4())
    invoice_id = record_data.get("customer_id", workflow_id)

    workflow = WorkflowRun(
        id=workflow_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        status="PENDING",
        current_stage=None,
        retry_count=0,
    )
    db.add(workflow)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another request created the workflow concurrently - return existing
        existing = db.query(WorkflowRun).filter_by(invoice_id=invoice_id).first()
        if existing:
            logger.info(
                "workflow_create_concurrent_duplicate",
                workflow_id=existing.id,
                customer_id=customer_id,
            )
            return existing
        raise
    db.refresh(workflow)
    logger.info("workflow_created", workflow_id=workflow_id, customer_id=customer_id)
    return workflow


def check_duplicate_submission(db: Session, customer_id: str) -> WorkflowRun | None:
    """Check if a workflow already exists for this customer (idempotency)."""
    return db.query(WorkflowRun).filter_by(invoice_id=customer_id).first()


def reset_workflow(db: Session, workflow_id: str):
    """Reset a workflow to reprocess from scratch. Clears old stage results."""
    workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
    if workflow:
        workflow.status = "PENDING"
        workflow.current_stage = None
        workflow.retry_count = 0
        workflow.updated_at = datetime.now(timezone.utc)
        db.query(WorkflowStageState).filter_by(workflow_id=workflow_id).delete()
        db.commit()
        logger.info("workflow_reset", workflow_id=workflow_id)


# --- Functions used by the background pipeline (use their own session) ---


def update_workflow_stage(workflow_id: str, stage: str, status: str):
    """Update the workflow's current stage and status."""
    with get_db_session() as db:
        workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.current_stage = stage
            workflow.status = status
            workflow.updated_at = datetime.now(timezone.utc)


def save_stage_result(
    workflow_id: str,
    stage_name: str,
    status: str,
    output: dict | None = None,
    error: str | None = None,
):
    """Persist the result of a stage execution."""
    with get_db_session() as db:
        stage_state = WorkflowStageState(
            workflow_id=workflow_id,
            stage_name=stage_name,
            status=status,
            output_json=json.dumps(output) if output else None,
            error_message=error,
        )
        db.add(stage_state)


def increment_retry(workflow_id: str):
    """Increment the retry count for a workflow."""
    with get_db_session() as db:
        workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.retry_count += 1
            workflow.updated_at = datetime.now(timezone.utc)


def mark_workflow_complete(workflow_id: str):
    """Mark workflow as successfully completed."""
    with get_db_session() as db:
        workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.status = "COMPLETED"
            workflow.updated_at = datetime.now(timezone.utc)
    logger.info("workflow_completed", workflow_id=workflow_id)


def mark_workflow_failed(workflow_id: str, error: str):
    """Mark workflow as permanently failed."""
    with get_db_session() as db:
        workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.status = "FAILED"
            workflow.updated_at = datetime.now(timezone.utc)
    logger.error("workflow_failed", workflow_id=workflow_id, error=error)

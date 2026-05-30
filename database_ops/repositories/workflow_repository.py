


import json
import uuid
from datetime import UTC, datetime, timedelta
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from structlog import get_logger
from database_ops.model import WorkflowRun, WorkflowRunStatus, WorkflowStageState

logger = get_logger()


class WorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_workflow(self, workflow_data) -> WorkflowRun:
        """Create a new workflow run. Returns existing if concurrent duplicate."""
        workflow_id = str(uuid.uuid4())
        workflow_run = WorkflowRun(
            id=workflow_id,
            customer_id=workflow_data.customer_id,
            status=WorkflowRunStatus.PENDING,
            current_stage=None,
            retry_count=0,
            raw_data=workflow_data.dict(),
        )
        self.db.add(workflow_run)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # Another request created the workflow concurrently - return existing
            existing = self.db.query(WorkflowRun).filter_by(customer_id=workflow_data.customer_id).first()
            if existing:
                logger.info(
                    "workflow_create_concurrent_duplicate",
                    workflow_id=existing.id,
                    customer_id=workflow_data.customer_id,
                )
                return existing
            raise
        self.db.refresh(workflow_run)
        logger.info("workflow_created", workflow_id=workflow_id, customer_id=workflow_data.customer_id)
        return workflow_run

    def get_workflow_by_customer_id(self, customer_id: str) -> WorkflowRun | None:
        """Return the first workflow run for a given customer_id, or None if not found."""
        return self.db.query(WorkflowRun).filter_by(customer_id=customer_id).first()

    def get_workflow_by_id(self, workflow_id: str):
        return self.db.query(WorkflowRun).filter_by(id=workflow_id).first()

    def get_stage_states(self, workflow_id: str):
        return (
            self.db.query(WorkflowStageState)
            .filter_by(workflow_id=workflow_id)
            .order_by(WorkflowStageState.updated_at)
            .all()
        )

    def get_stats(self, stale_minutes: int):
        now = datetime.now(UTC)
        stale_cutoff = now - timedelta(minutes=stale_minutes)
        total = self.db.query(func.count(WorkflowRun.id)).scalar() or 0
        completed = (
            self.db.query(func.count(WorkflowRun.id))
            .filter(WorkflowRun.status == WorkflowRunStatus.SUCCESS)
            .scalar()
            or 0
        )
        failed = (
            self.db.query(func.count(WorkflowRun.id))
            .filter(WorkflowRun.status == WorkflowRunStatus.FAILED)
            .scalar()
            or 0
        )
        pending = (
            self.db.query(func.count(WorkflowRun.id))
            .filter(WorkflowRun.status == WorkflowRunStatus.PENDING)
            .scalar()
            or 0
        )
        running = (
            self.db.query(func.count(WorkflowRun.id))
            .filter(WorkflowRun.status == WorkflowRunStatus.RUNNING)
            .scalar()
            or 0
        )
        stale = (
            self.db.query(func.count(WorkflowRun.id))
            .filter(
                WorkflowRun.status == WorkflowRunStatus.FAILED,
                WorkflowRun.updated_at < stale_cutoff,
            )
            .scalar()
            or 0
        )
        return dict(
            total=total,
            completed=completed,
            failed=failed,
            pending=pending,
            running=running,
            stale=stale,
        )

    def reset_workflow(self, workflow_id: str):
        """Reset a workflow to reprocess from scratch. Clears old stage results."""
        workflow = self.db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.status = WorkflowRunStatus.PENDING
            workflow.current_stage = None
            workflow.retry_count = 0
            workflow.updated_at = datetime.now(UTC)
            self.db.query(WorkflowStageState).filter_by(workflow_id=workflow_id).delete()
            self.db.commit()
            logger.info("workflow_reset", workflow_id=workflow_id)

    def update_workflow_stage(self, workflow_id: str, stage, status):
        """Update the workflow's current stage and status."""
        workflow = self.db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.current_stage = stage
            workflow.status = status
            workflow.updated_at = datetime.now(UTC)
            self.db.commit()

    def save_stage_result(self, workflow_id: str, customer_id: str, stage_name, status, output=None, error=None):
        """Persist the result of a stage execution."""
        stage_state = WorkflowStageState(
            workflow_id=workflow_id,
            customer_id=customer_id,
            stage_name=stage_name,
            status=status,
            output_json=json.dumps(output) if output else None,
            error_message=error,
        )
        self.db.add(stage_state)
        self.db.commit()

    def increment_retry(self, workflow_id: str):
        """Increment the retry count for a workflow."""
        workflow = self.db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.retry_count += 1
            workflow.updated_at = datetime.now(UTC)
            self.db.commit()

    def mark_workflow_complete(self, workflow_id: str):
        """Mark workflow as successfully completed."""
        workflow = self.db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.status = WorkflowRunStatus.COMPLETED
            workflow.updated_at = datetime.now(UTC)
            self.db.commit()
        logger.info("workflow_completed", workflow_id=workflow_id)

    def mark_workflow_failed(self, workflow_id: str, error: str):
        """Mark workflow as permanently failed."""
        workflow = self.db.query(WorkflowRun).filter_by(id=workflow_id).first()
        if workflow:
            workflow.status = WorkflowRunStatus.FAILED
            workflow.updated_at = datetime.now(UTC)
            self.db.commit()
        logger.error("workflow_failed", workflow_id=workflow_id, error=error)

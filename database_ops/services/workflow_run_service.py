from sqlalchemy.orm import Session

from database_ops.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStageName,
)
from database_ops.repositories.workflow_run_repository import (
    WorkflowRunRepository,
)
from database_ops.validations.workflow_run_validator import (
    WorkflowRunValidator,
)


class WorkflowRunService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = WorkflowRunRepository(db)

    def create_workflow(
        self,
        customer_id: str,
    ) -> WorkflowRun:

        existing = self.repo.get_by_customer_id(customer_id)

        if existing:
            return existing

        workflow = WorkflowRun(
            customer_id=customer_id,
            status=WorkflowRunStatus.PENDING,
            current_stage=WorkflowStageName.INGESTION,
        )

        return self.repo.create(workflow)

    def get_workflow(
        self,
        workflow_id: str,
    ) -> WorkflowRun | None:
        return self.repo.get_by_id(workflow_id)

    def start_workflow(
        self,
        workflow_id: str,
    ) -> WorkflowRun:

        workflow = self.repo.get_by_id(
            workflow_id,
            lock_for_update=True,
        )

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        WorkflowRunValidator.validate_status_transition(
            workflow.status,
            WorkflowRunStatus.RUNNING,
        )

        return self.repo.update_status(
            workflow,
            WorkflowRunStatus.RUNNING,
        )

    def update_stage(
        self,
        workflow_id: str,
        stage: WorkflowStageName,
    ) -> WorkflowRun:

        workflow = self.repo.get_by_id(
            workflow_id,
            lock_for_update=True,
        )

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        return self.repo.update_stage(
            workflow,
            stage,
        )

    def mark_completed(
        self,
        workflow_id: str,
    ) -> WorkflowRun:

        workflow = self.repo.get_by_id(
            workflow_id,
            lock_for_update=True,
        )

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        WorkflowRunValidator.validate_status_transition(
            workflow.status,
            WorkflowRunStatus.COMPLETED,
        )

        return self.repo.update_status(
            workflow,
            WorkflowRunStatus.COMPLETED,
        )

    def mark_failed(
        self,
        workflow_id: str,
    ) -> WorkflowRun:

        workflow = self.repo.get_by_id(
            workflow_id,
            lock_for_update=True,
        )

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        WorkflowRunValidator.validate_status_transition(
            workflow.status,
            WorkflowRunStatus.FAILED,
        )

        return self.repo.update_status(
            workflow,
            WorkflowRunStatus.FAILED,
        )

    def retry_workflow(
        self,
        workflow_id: str,
    ) -> WorkflowRun:

        workflow = self.repo.get_by_id(
            workflow_id,
            lock_for_update=True,
        )

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        WorkflowRunValidator.validate_status_transition(
            workflow.status,
            WorkflowRunStatus.RETRYING,
        )

        self.repo.increment_retry_count(workflow)

        return self.repo.update_status(
            workflow,
            WorkflowRunStatus.RETRYING,
        )

    def get_workflow_by_customer_id(
        self,
        customer_id: str,
    ) -> WorkflowRun | None:
        """
        Returns the most recently updated WorkflowRun for the given customer_id.
        """
        return self.repo.get_latest_by_customer_id(customer_id)

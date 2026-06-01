from sqlalchemy.orm import Session

from database_ops.models import (
    WorkflowRunStatus,
    WorkflowStageName,
    WorkflowStageState,
)
from database_ops.repositories.workflow_stage_state_repository import (
    WorkflowStageStateRepository,
)


class WorkflowStageStateService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = WorkflowStageStateRepository(db)

    def create_stage_state(
        self,
        workflow_id: str,
        stage_name: WorkflowStageName,
        retry_count: int = 0,
        status: WorkflowRunStatus = WorkflowRunStatus.PENDING,
        output_json: str | None = None,
        error_message: str | None = None,
    ) -> WorkflowStageState:

        stage_state = WorkflowStageState(
            workflow_id=workflow_id,
            stage_name=stage_name,
            retry_count=retry_count,
            status=status,
            output_json=output_json,
            error_message=error_message,
        )

        return self.repo.create(stage_state)

    def get_stage_state(
        self,
        workflow_id: str,
        stage_name: WorkflowStageName,
    ) -> WorkflowStageState | None:
        """Get stage state by workflow ID and stage name."""
        return self.repo.get_by_workflow_and_stage(
            workflow_id,
            stage_name,
        )

    def update_status(
        self,
        workflow_id: str,
        stage_name: WorkflowStageName,
        status: WorkflowRunStatus,
        output_json: str | None = None,
        error_message: str | None = None,
    ) -> WorkflowStageState:
        stage_state = self.get_stage_state(
            workflow_id,
            stage_name,
        )

        if not stage_state:
            raise ValueError(f"Stage state not found: {workflow_id} {stage_name}")

        stage_state.status = status
        stage_state.output_json = output_json
        stage_state.error_message = error_message

        return self.repo.update(stage_state)

    def increment_retry(
        self,
        workflow_id: str,
        stage_name: WorkflowStageName,
    ) -> WorkflowStageState:
        stage_state = self.get_stage_state(
            workflow_id,
            stage_name,
        )

        if not stage_state:
            raise ValueError(f"Stage state not found: {workflow_id} {stage_name}")

        stage_state.retry_count += 1

        return self.repo.update(stage_state)

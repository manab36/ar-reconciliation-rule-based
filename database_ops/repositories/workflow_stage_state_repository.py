from sqlalchemy.orm import Session

from database_ops.models import WorkflowStageName, WorkflowStageState


class WorkflowStageStateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, workflow_stage_state: WorkflowStageState) -> WorkflowStageState:
        """Create a new workflow stage state."""
        self.db.add(workflow_stage_state)
        self.db.flush()
        self.db.refresh(workflow_stage_state)
        return workflow_stage_state

    def get_by_id(self, stage_state_id: str) -> WorkflowStageState | None:
        """Get workflow stage state by ID."""
        return (
            self.db.query(WorkflowStageState)
            .filter(WorkflowStageState.id == stage_state_id)
            .first()
        )

    def get_by_workflow_id(self, workflow_id: str) -> list[WorkflowStageState]:
        """Get all stage states for a workflow."""
        return (
            self.db.query(WorkflowStageState)
            .filter(WorkflowStageState.workflow_id == workflow_id)
            .all()
        )

    def get_by_workflow_and_stage(
        self,
        workflow_id: str,
        stage_name: WorkflowStageName,
    ) -> WorkflowStageState | None:
        """Get stage state by workflow ID and stage name."""
        return (
            self.db.query(WorkflowStageState)
            .filter(
                WorkflowStageState.workflow_id == workflow_id,
                WorkflowStageState.stage_name == stage_name,
            )
            .first()
        )

    def update(self, stage_state: WorkflowStageState) -> WorkflowStageState:
        """Update a workflow stage state."""
        self.db.add(stage_state)
        self.db.flush()
        self.db.refresh(stage_state)
        return stage_state

    def delete(self, stage_state: WorkflowStageState) -> None:
        """Delete a workflow stage state."""
        self.db.delete(stage_state)

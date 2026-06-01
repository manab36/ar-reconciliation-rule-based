from database_ops.models import (
    WorkflowRunStatus,
)


class WorkflowRunValidator:
    ALLOWED_TRANSITIONS = {
        WorkflowRunStatus.PENDING: [
            WorkflowRunStatus.RUNNING,
        ],
        WorkflowRunStatus.RUNNING: [
            WorkflowRunStatus.COMPLETED,
            WorkflowRunStatus.FAILED,
        ],
        WorkflowRunStatus.FAILED: [
            WorkflowRunStatus.RETRYING,
        ],
        WorkflowRunStatus.RETRYING: [
            WorkflowRunStatus.RUNNING,
        ],
        WorkflowRunStatus.COMPLETED: [],
    }

    @classmethod
    def validate_status_transition(
        cls,
        current_status,
        new_status,
    ):

        allowed = cls.ALLOWED_TRANSITIONS.get(
            current_status,
            [],
        )

        if new_status not in allowed:
            raise ValueError(f"Invalid transition {current_status} -> {new_status}")

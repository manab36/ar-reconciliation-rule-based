from sqlalchemy import select
from sqlalchemy.orm import Session

from database_ops.models import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStageName,
)


class WorkflowRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        workflow_run: WorkflowRun,
    ) -> WorkflowRun:

        self.db.add(workflow_run)
        self.db.flush()

        return workflow_run

    def get_by_id(
        self,
        workflow_id: str,
        lock_for_update: bool = False,
    ) -> WorkflowRun | None:

        stmt = select(WorkflowRun).where(WorkflowRun.id == workflow_id)

        if lock_for_update:
            stmt = stmt.with_for_update()

        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_customer_id(
        self,
        customer_id: str,
        lock_for_update: bool = False,
    ) -> WorkflowRun | None:

        stmt = select(WorkflowRun).where(WorkflowRun.customer_id == customer_id)

        if lock_for_update:
            stmt = stmt.with_for_update()

        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self) -> list[WorkflowRun]:

        stmt = select(WorkflowRun)

        return list(self.db.execute(stmt).scalars().all())

    def update_status(
        self,
        workflow: WorkflowRun,
        status: WorkflowRunStatus,
    ) -> WorkflowRun:

        workflow.status = status

        self.db.flush()

        return workflow

    def update_stage(
        self,
        workflow: WorkflowRun,
        stage: WorkflowStageName,
    ) -> WorkflowRun:

        workflow.current_stage = stage

        self.db.flush()

        return workflow

    def increment_retry_count(
        self,
        workflow: WorkflowRun,
    ) -> WorkflowRun:

        workflow.retry_count += 1

        self.db.flush()

        return workflow

    def delete(
        self,
        workflow: WorkflowRun,
    ) -> None:

        self.db.delete(workflow)
        self.db.flush()

    def get_latest_by_customer_id(
        self,
        customer_id: str,
        lock_for_update: bool = False,
    ) -> WorkflowRun | None:
        """
        Returns the most recently updated WorkflowRun for a customer_id.
        """
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.customer_id == customer_id)
            .order_by(WorkflowRun.updated_at.desc())
        )
        if lock_for_update:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalars().first()

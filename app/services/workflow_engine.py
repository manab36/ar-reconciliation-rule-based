


import structlog
from sqlalchemy.orm import Session
from app.core.database import get_db_session
from database_ops.model import WorkflowRun, WorkflowRunStatus, WorkflowStageName
from database_ops.repositories.workflow_repository import WorkflowRepository
from database_ops.repositories.customer_repository import CustomerRepository
from pydantic import BaseModel
from app.core.config import Settings

class WorkflowCreate(BaseModel):
    customer_id: str
    record_data: dict

class StageStateModel(BaseModel):
    workflow_id: str
    stage_name: WorkflowStageName
    status: WorkflowRunStatus
    output: dict | None = None
    error: str | None = None


logger = structlog.get_logger()

# Load pipeline stages from config
settings = Settings()
STAGES = settings.AR_RECONCILIATION_PIPELINE_STAGES


def get_next_stage(current: WorkflowStageName | str | None) -> WorkflowStageName | None:
    """Return the next stage in the pipeline, or None if complete."""
    if current is None:
        return WorkflowStageName.INGESTION
    if isinstance(current, WorkflowStageName):
        current = current.value
    try:
        idx = STAGES.index(current)
    except ValueError:
        logger.error("invalid_current_stage", current_stage=current)
        return None
    if idx + 1 >= len(STAGES):
        return None
    return WorkflowStageName(STAGES[idx + 1])


def create_workflow(db: Session, workflow: WorkflowCreate) -> WorkflowRun:
    """Create a new workflow run. Returns existing if concurrent duplicate."""
    # Check if customer exists using CustomerRepository
    customer_repo = CustomerRepository(db)
    customer = customer_repo.get_customer_by_id(workflow.customer_id)
    if not customer:
        name = getattr(workflow, "customer_name", None) or getattr(workflow, "name", None) or workflow.customer_id
        customer_repo.add_customer(id=workflow.customer_id, name=name)
    repo = WorkflowRepository(db)
    return repo.create_workflow(workflow)


def check_duplicate_submission(db: Session, customer_id: str) -> WorkflowRun | None:
    """Check if a workflow already exists for this customer (idempotency)."""
    repo = WorkflowRepository(db)
    return repo.get_workflow_by_customer_id(customer_id)


def reset_workflow(db: Session, workflow_id: str):
    """Reset a workflow to reprocess from scratch. Clears old stage results."""
    repo = WorkflowRepository(db)
    repo.reset_workflow(workflow_id)



# --- Functions used by the background pipeline (use their own session) ---
def update_workflow_stage(workflow_id: str, stage: WorkflowStageName | str, status: WorkflowRunStatus | str):
    """Update the workflow's current stage and status."""
    with get_db_session() as db:
        repo = WorkflowRepository(db)
        repo.update_workflow_stage(
            workflow_id,
            stage if isinstance(stage, WorkflowStageName) else WorkflowStageName(stage),
            status if isinstance(status, WorkflowRunStatus) else WorkflowRunStatus(status),
        )


def save_stage_result(
    workflow_id: str,
    customer_id: str,
    stage_name: WorkflowStageName | str,
    status: WorkflowRunStatus | str,
    output: dict | None = None,
    error: str | None = None,
):
    """Persist the result of a stage execution."""
    with get_db_session() as db:
        repo = WorkflowRepository(db)
        repo.save_stage_result(
            workflow_id,
            customer_id,
            stage_name if isinstance(stage_name, str) else stage_name.value,
            status if isinstance(status, WorkflowRunStatus) else WorkflowRunStatus(status),
            output,
            error,
        )


def increment_retry(workflow_id: str):
    """Increment the retry count for a workflow."""
    with get_db_session() as db:
        repo = WorkflowRepository(db)
        repo.increment_retry(workflow_id)


def mark_workflow_complete(workflow_id: str):
    """Mark workflow as successfully completed."""
    with get_db_session() as db:
        repo = WorkflowRepository(db)
        repo.mark_workflow_complete(workflow_id)


def mark_workflow_failed(workflow_id: str, error: str):
    """Mark workflow as permanently failed."""
    with get_db_session() as db:
        repo = WorkflowRepository(db)
        repo.mark_workflow_failed(workflow_id, error)

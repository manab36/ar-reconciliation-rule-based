import json

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.record import ARRecord
from app.models.workflow import WorkflowRun, WorkflowStageState
from app.schemas.workflow import (
    StageStateResponse,
    SubmitResponse,
    WorkflowDetailResponse,
    WorkflowResponse,
)
from app.services.pipeline import run_pipeline
from app.services.workflow_engine import get_next_stage

logger = structlog.get_logger()

router = APIRouter(tags=["workflows"])


@router.get("/workflow/{workflow_id}", response_model=WorkflowDetailResponse)
def get_workflow_status(workflow_id: str, db: Session = Depends(get_db)):
    """Get full workflow status including all stage states."""
    workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    stages = (
        db.query(WorkflowStageState)
        .filter_by(workflow_id=workflow_id)
        .order_by(WorkflowStageState.updated_at)
        .all()
    )

    return WorkflowDetailResponse(
        workflow=WorkflowResponse.model_validate(workflow),
        stages=[StageStateResponse.model_validate(s) for s in stages],
    )


@router.post("/resume/{workflow_id}", response_model=SubmitResponse)
def resume_workflow_endpoint(
    workflow_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """
    Resume a failed workflow from its last successful stage.
    Will not restart completed workflows.
    """
    workflow = db.query(WorkflowRun).filter_by(id=workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow.status == "COMPLETED":
        return SubmitResponse(
            workflow_id=workflow.id,
            status="COMPLETED",
            message="Workflow already completed",
        )

    # Reconstruct record_data from the stored AR record
    ar_record = db.query(ARRecord).filter_by(customer_id=workflow.customer_id).first()
    record_data = {}
    if ar_record:
        record_data = {
            "customer_id": ar_record.customer_id,
            "customer_name": ar_record.customer_name,
            "customer_balance": ar_record.customer_balance,
            "invoice_total": ar_record.invoice_total,
            "invoice_applied_amount": ar_record.invoice_applied_amount,
            "invoice_exchange_rate": ar_record.invoice_exchange_rate,
            "payment_total": ar_record.payment_total,
            "payment_applied_amount": ar_record.payment_applied_amount,
            "payment_exchange_rate": ar_record.payment_exchange_rate,
            "credit_total": ar_record.credit_total,
            "credit_applied_amount": ar_record.credit_applied_amount,
            "credit_exchange_rate": ar_record.credit_exchange_rate,
            "adjustment_total": ar_record.adjustment_total,
            "adjustment_applied_amount": ar_record.adjustment_applied_amount,
            "adjustment_exchange_rate": ar_record.adjustment_exchange_rate,
        }

    # Re-populate stage outputs for downstream stages
    successful_stages = (
        db.query(WorkflowStageState)
        .filter_by(workflow_id=workflow_id, status="SUCCESS")
        .all()
    )
    for stage_state in successful_stages:
        if stage_state.output_json:
            output = json.loads(stage_state.output_json)
            if stage_state.stage_name == "matching":
                record_data["_match_result"] = output.get("match_result")
            elif stage_state.stage_name == "validation":
                record_data["_is_valid"] = output.get("is_valid")

    next_stage = get_next_stage(workflow.current_stage)
    if next_stage is None:
        return SubmitResponse(
            workflow_id=workflow.id,
            status="COMPLETED",
            message="Workflow already completed all stages",
        )

    background_tasks.add_task(run_pipeline, workflow_id, next_stage, record_data)

    return SubmitResponse(
        workflow_id=workflow.id,
        status="RESUMING",
        message=f"Workflow resuming from after stage: {workflow.current_stage}",
    )


@router.get("/workflows", response_model=list[WorkflowResponse])
def list_workflows(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List workflows with optional status filter."""
    query = db.query(WorkflowRun)
    if status:
        query = query.filter_by(status=status)
    workflows = (
        query.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()
    )
    return [WorkflowResponse.model_validate(w) for w in workflows]

import json

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.workflow import (
    StageStateResponse,
    SubmitResponse,
    WorkflowDetailResponse,
    WorkflowResponse,
    RecordSubmit,
)
from typing import Optional
from app.services.pipeline import PipelineRunner
from app.services.workflow_engine import get_next_stage
from database_ops.model import WorkflowRunStatus
from database_ops.repositories.record_repository import RecordRepository
from database_ops.repositories.workflow_repository import WorkflowRepository

logger = structlog.get_logger()

router = APIRouter(tags=["workflows"])


# @router.get("/workflow/{workflow_id}", response_model=WorkflowDetailResponse)
# def get_workflow_status(workflow_id: str, db: Session = Depends(get_db)):
#     """Get full workflow status including all stage states."""
#     workflow_repo = WorkflowRepository(db)
#     workflow = workflow_repo.get_workflow_by_id(workflow_id)
#     if not workflow:
#         raise HTTPException(status_code=404, detail="Workflow not found")

#     stages = workflow_repo.get_stage_states(workflow_id)

#     return WorkflowDetailResponse(
#         workflow=WorkflowResponse.model_validate(workflow),
#         stages=[StageStateResponse.model_validate(s) for s in stages],
#     )


# @router.post("/resume/{workflow_id}", response_model=SubmitResponse)
# def resume_workflow_endpoint(
#     workflow_id: str,
#     record: Optional[RecordSubmit] = None,
#     background_tasks: BackgroundTasks = None,
#     db: Session = Depends(get_db),
# ):
#     """
#     Resume a failed workflow from its last successful stage.
#     Will not restart completed workflows.
#     """
#     workflow_repo = WorkflowRepository(db)
#     record_repo = RecordRepository(db)
#     workflow = workflow_repo.get_workflow_by_id(workflow_id)
#     if not workflow:
#         raise HTTPException(status_code=404, detail="Workflow not found")

#     if workflow.status == WorkflowRunStatus.SUCCESS:
#         return SubmitResponse(
#             workflow_id=workflow.id,
#             status=WorkflowRunStatus.SUCCESS,
#             message="Workflow already completed",
#         )

#     # Use provided record if present, else reconstruct from DB
#     if record:
#         record_data = record.model_dump()
#     else:
#         ar_record = record_repo.get_ar_record_by_customer_id(workflow.customer_id)
#         record_data = {}
#         if ar_record:
#             record_data = {
#                 "customer_id": ar_record.customer_id,
#                 "customer_name": ar_record.customer_name,
#                 "customer_balance": ar_record.customer_balance,
#                 "invoice_total": ar_record.invoice_total,
#                 "invoice_applied_amount": ar_record.invoice_applied_amount,
#                 "invoice_exchange_rate": ar_record.invoice_exchange_rate,
#                 "payment_total": ar_record.payment_total,
#                 "payment_applied_amount": ar_record.payment_applied_amount,
#                 "payment_exchange_rate": ar_record.payment_exchange_rate,
#                 "credit_total": ar_record.credit_total,
#                 "credit_applied_amount": ar_record.credit_applied_amount,
#                 "credit_exchange_rate": ar_record.credit_exchange_rate,
#                 "adjustment_total": ar_record.adjustment_total,
#                 "adjustment_applied_amount": ar_record.adjustment_applied_amount,
#                 "adjustment_exchange_rate": ar_record.adjustment_exchange_rate,
#             }

#     # Re-populate stage outputs for downstream stages
#     successful_stages = [
#         s
#         for s in workflow_repo.get_stage_states(workflow_id)
#         if s.status == WorkflowRunStatus.SUCCESS
#     ]
#     for stage_state in successful_stages:
#         if stage_state.output_json:
#             output = json.loads(stage_state.output_json)
#             if stage_state.stage_name == "matching":
#                 record_data["_match_result"] = output.get("match_result")
#             elif stage_state.stage_name == "validation":
#                 record_data["_is_valid"] = output.get("is_valid")

#     next_stage = get_next_stage(workflow.current_stage)
#     if next_stage is None:
#         return SubmitResponse(
#             workflow_id=workflow.id,
#             status=WorkflowRunStatus.SUCCESS,
#             message="Workflow already completed all stages",
#         )

#     background_tasks.add_task(run_pipeline, workflow_id, next_stage, record_data)

#     return SubmitResponse(
#         workflow_id=workflow.id,
#         status=WorkflowRunStatus.RUNNING,
#         message=f"Workflow resuming from after stage: {workflow.current_stage}",
#     )


# @router.get("/workflows", response_model=list[WorkflowResponse])
# def list_workflows(
#     status: WorkflowRunStatus | None = None,
#     limit: int = Query(default=50, ge=1, le=200),
#     offset: int = Query(default=0, ge=0),
#     db: Session = Depends(get_db),
# ):
#     """List workflows with optional status filter."""
#     workflow_repo = WorkflowRepository(db)
#     # For now, keep the original logic, but you can add a method in WorkflowRepository for this
#     if status:
#         db.query(workflow_repo).filter_by(status=status)
#     workflows = (
#         db.query(workflow_repo)
#         .order_by(workflow_repo.created_at.desc())
#         .offset(offset)
#         .limit(limit)
#         .all()
#     )
#     return [WorkflowResponse.model_validate(w) for w in workflows]

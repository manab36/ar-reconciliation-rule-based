

import csv
import io
import json
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.workflow import StatsResponse, WorkflowListItem
from database_ops.model import WorkflowRun, WorkflowRunStatus, WorkflowStageState, WorkflowStageName
from database_ops.repositories.workflow_repository import WorkflowRepository

logger = structlog.get_logger()

router = APIRouter(tags=["dashboard"])


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """Dashboard stats: workflow counts by status and routing decisions."""
    workflow_repo = WorkflowRepository(db)
    stats = workflow_repo.get_stats(settings.STALE_MINUTES)
    # The following logic for decisions is still done here, but can be moved to repo if needed
    from database_ops.model import WorkflowStageState

    decision_stages = (
        db.query(WorkflowStageState.output_json)
        .filter(
            WorkflowStageState.stage_name == "decision_routing",
            WorkflowStageState.status == WorkflowRunStatus.SUCCESS,
        )
        .all()
    )
    decisions: dict[str, int] = {}
    for (output_json,) in decision_stages:
        if output_json:
            output = json.loads(output_json)
            decision = output.get("decision", "UNKNOWN")
            decisions[decision] = decisions.get(decision, 0) + 1

    return StatsResponse(
        total_workflows=stats["total"],
        completed=stats["completed"],
        failed=stats["failed"],
        pending=stats["pending"],
        running=stats["running"],
        stale=stats["stale"],
        decisions=decisions,
    )


@router.get("/workflows/enhanced", response_model=list[WorkflowListItem])
def list_workflows_enhanced(
    status: WorkflowRunStatus | None = None,
    stale_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List workflows with staleness flag and last error message."""
    query = db.query(WorkflowRun)
    if status:
        query = query.filter_by(status=status)

    stale_cutoff = datetime.now(UTC) - timedelta(minutes=settings.STALE_MINUTES)

    if stale_only:
        query = query.filter(
            WorkflowRun.status == WorkflowRunStatus.FAILED,
            WorkflowRun.updated_at < stale_cutoff,
        )

    workflows = (
        query.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()
    )

    # Batch-load last errors for all workflows in one query
    workflow_ids = [w.id for w in workflows]
    failed_stages = (
        db.query(WorkflowStageState)
        .filter(
            WorkflowStageState.workflow_id.in_(workflow_ids),
            WorkflowStageState.status == WorkflowRunStatus.FAILED,
        )
        .order_by(WorkflowStageState.updated_at.desc())
        .all()
    )
    # Map: workflow_id -> latest error (first encountered due to desc order)
    error_map: dict[str, str] = {}
    for stage in failed_stages:
        if stage.workflow_id not in error_map and stage.error_message:
            error_map[stage.workflow_id] = stage.error_message

    results = []
    for w in workflows:
        is_stale = (
            w.status == WorkflowRunStatus.FAILED
            and w.updated_at is not None
            and w.updated_at < stale_cutoff
        )

        results.append(
            WorkflowListItem(
                id=w.id,
                customer_id=w.customer_id,
                status=w.status if isinstance(w.status, WorkflowRunStatus) else WorkflowRunStatus[w.status],
                current_stage=w.current_stage if isinstance(w.current_stage, WorkflowStageName) or w.current_stage is None else WorkflowStageName[w.current_stage],
                retry_count=w.retry_count,
                is_stale=is_stale,
                last_error=error_map.get(w.id),
                created_at=w.created_at,
                updated_at=w.updated_at,
            )
        )

    return results


@router.get("/export")
def export_results(db: Session = Depends(get_db)):
    """Export all completed workflow results as a CSV download."""
    # JOIN workflows with their routing stage in one query (avoids N+1)
    rows = (
        db.query(WorkflowRun, WorkflowStageState.output_json)
        .outerjoin(
            WorkflowStageState,
            (WorkflowStageState.workflow_id == WorkflowRun.id)
            & (WorkflowStageState.stage_name == "decision_routing")
            & (WorkflowStageState.status == WorkflowRunStatus.SUCCESS),
        )
        .filter(WorkflowRun.status == WorkflowRunStatus.SUCCESS)
        .order_by(WorkflowRun.created_at)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "workflow_id",
            "customer_id",
            "status",
            "match_result",
            "is_valid",
            "decision",
            "high_value",
            "retry_count",
            "completed_at",
        ]
    )

    for workflow, output_json in rows:
        match_result = decision = ""
        is_valid = high_value = ""
        if output_json:
            data = json.loads(output_json)
            match_result = data.get("match_result", "")
            decision = data.get("decision", "")
            is_valid = str(data.get("is_valid", ""))
            high_value = str(data.get("high_value", ""))

        writer.writerow(
            [
                workflow.id,
                workflow.customer_id,
                workflow.status.value if isinstance(workflow.status, WorkflowRunStatus) else workflow.status,
                match_result,
                is_valid,
                decision,
                high_value,
                workflow.retry_count,
                workflow.updated_at,
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ar_results.csv"},
    )

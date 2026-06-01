import json
import uuid
from datetime import UTC, datetime
from importlib import import_module

import structlog
from fastapi import APIRouter

from app.core.database import get_db_session
from app.services.ar_reconciliation_pipeline.pipeline_config import (
    AR_RECONCILIATION_PIPELINE_STAGES,
)
from database_ops.models import (
    ARRecord,
    WorkflowRunStatus,
    WorkflowStageName,
    WorkflowStageState,
)
from database_ops.repositories.workflow_run_repository import WorkflowRunRepository
from database_ops.repositories.workflow_stage_state_repository import (
    WorkflowStageStateRepository,
)
from database_ops.services.ar_record_service import ARRecordService
from database_ops.services.processed_record_service import ProcessedRecordService

logger = structlog.get_logger()
router = APIRouter(tags=["run_ar_pipeline"])


class PipelineRunner:
    """
    Pipeline runner for AR reconciliation workflow.

    Handles:
        - Stage-by-stage execution with retry logic
        - Checkpoint-based resume from failed stages
        - Final output persistence to ProcessedRecord table
    """

    def __init__(
        self,
        workflow_id: str,
        customer_id: str | None = None,
        stage: WorkflowStageName | None = None,
    ):
        self.workflow_id = workflow_id
        self.customer_id = customer_id
        self.current_stage = stage if stage else WorkflowStageName.INGESTION
        self.processing_started_at = datetime.now(UTC)

        # If first stage, load ARRecord as dict for processing
        if self.__is_first_stage() and self.customer_id:
            with get_db_session() as db:
                ar_record = (
                    db.query(ARRecord).filter_by(customer_id=self.customer_id).first()
                )
                if ar_record:
                    # Convert SQLAlchemy models to dict
                    self.current_processed_data = {
                        c.name: getattr(ar_record, c.name)
                        for c in ar_record.__table__.columns
                    }
                else:
                    self.current_processed_data = {}
        else:
            self.current_processed_data = {}
        self.current_workflow_stage_id = None  # Only store the ID, never the ORM object
        self._validate()

    def _validate(self) -> None:
        """Validate workflow ID is a valid UUID."""
        try:
            uuid.UUID(str(self.workflow_id))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"workflow_id '{self.workflow_id}' is not a valid UUID."
            ) from exc

    def __is_first_stage(self) -> bool:
        """Return True if the current stage is the first stage in the pipeline."""
        stages = list(AR_RECONCILIATION_PIPELINE_STAGES.keys())
        return self.current_stage == stages[0]

    def __is_last_stage(self) -> bool:
        return self._get_next_stage(self.current_stage) is None

    def _get_previous_stage(
        self, current_stage: WorkflowStageName
    ) -> WorkflowStageName | None:
        """Return the stage before the given stage, or None if it's the first stage."""
        stages = list(AR_RECONCILIATION_PIPELINE_STAGES.keys())
        current_index = stages.index(current_stage)
        if current_index == 0:
            return None
        return stages[current_index - 1]

    def _load_previous_stage_output(self) -> dict:
        """
        Load the output from the previous stage from the database.
        This is used when resuming a pipeline from a failed stage.

        Returns:
            dict: The output_json from the previous stage, or empty dict if not found.
        """
        previous_stage = self._get_previous_stage(self.current_stage)
        if previous_stage is None:
            # This is the first stage, no previous output to load
            logger.debug(
                "no_previous_stage",
                workflow_id=self.workflow_id,
                current_stage=self.current_stage.value,
            )
            return {}

        with get_db_session() as db:
            stage_state_repo = WorkflowStageStateRepository(db)
            stage_state = stage_state_repo.get_by_workflow_and_stage(
                self.workflow_id, previous_stage
            )

            if stage_state and stage_state.output_json:
                try:
                    output_data = json.loads(stage_state.output_json)
                    logger.info(
                        "loaded_previous_stage_output",
                        workflow_id=self.workflow_id,
                        previous_stage=previous_stage.value,
                        current_stage=self.current_stage.value,
                    )
                    return output_data
                except json.JSONDecodeError as e:
                    logger.error(
                        "failed_to_parse_previous_stage_output",
                        workflow_id=self.workflow_id,
                        previous_stage=previous_stage.value,
                        error=str(e),
                    )
                    return {}
            else:
                logger.warning(
                    "previous_stage_output_not_found",
                    workflow_id=self.workflow_id,
                    previous_stage=previous_stage.value,
                    current_stage=self.current_stage.value,
                )
                return {}

    def _ensure_data_available(self) -> None:
        """
        Ensure that current_processed_data is available for the current stage.
        If starting from a non-first stage and data is empty, load from previous stage's DB output.
        """
        if self.current_processed_data:
            # Data already available, nothing to do
            return

        if self.__is_first_stage():
            # First stage with no data - this is an error condition
            if not self.customer_id:
                logger.warning(
                    "first_stage_no_customer_id",
                    workflow_id=self.workflow_id,
                )
            return

        # Non-first stage with no data - load from previous stage's output in DB
        logger.info(
            "loading_data_for_resume",
            workflow_id=self.workflow_id,
            current_stage=self.current_stage.value,
        )
        self.current_processed_data = self._load_previous_stage_output()

    def __get_ar_record_id(self):
        with get_db_session() as db:
            service = ARRecordService(db)
            ar_record = service.get_record_by_customer_id(self.customer_id)
            return ar_record.id if ar_record else None

    def __handle_pipeline_failure(self, error: Exception):
        """
        Handles pipeline failure by updating workflow_run and workflow_stage_state tables.
        Use cases handled:
            1. Update the workflow_run table:
                a. Set status to FAILED
                b. Set current stage
                c. Increment retry count
            2. Update the workflow_stage_state table:
                a. For self.current_workflow_stage_id, mark as FAILED
                b. Set error message
                c. Update timestamp
            3. Robust to missing stage state id
        """
        with get_db_session() as db:
            # Update WorkflowRun
            workflow_repo = WorkflowRunRepository(db)
            workflow_run = workflow_repo.get_by_id(
                self.workflow_id, lock_for_update=True
            )
            if workflow_run:
                workflow_run.status = WorkflowRunStatus.FAILED
                workflow_run.current_stage = self.current_stage
                workflow_run.retry_count += 1
                db.flush()

            # Update workflow_stage_state if possible
            if self.current_workflow_stage_id:
                stage_state_repo = WorkflowStageStateRepository(db)
                stage_state = stage_state_repo.get_by_id(self.current_workflow_stage_id)
                if stage_state:
                    stage_state.status = WorkflowRunStatus.FAILED
                    stage_state.error_message = str(error)
                    stage_state.updated_at = datetime.now(UTC)
                    db.flush()

        logger.error(
            "stage_failed",
            workflow_id=self.workflow_id,
            stage=self.current_stage.value,
            error=str(error),
        )
        if self.current_workflow_stage_id:
            logger.error(
                "stage_state_failed",
                workflow_id=self.workflow_id,
                stage=self.current_stage.value,
                stage_state_id=self.current_workflow_stage_id,
                error=str(error),
            )

    def __handle_pipeline_retry(self, error: Exception, attempt: int):
        """
        Handles pipeline retry logic by incrementing retry counts and logging retry attempts.
        Ensures all ORM access is within the session context to avoid detached instance errors.
        Adds detailed debug logs for troubleshooting.
        """
        # Removed verbose debug log: pipeline_retry_entered
        # Prepare primitive values for logging
        workflow_run_id = None
        workflow_run_stage = None
        workflow_run_retry_count = None
        try:
            with get_db_session() as db:
                now = datetime.now(UTC)
                stage_state_repo = WorkflowStageStateRepository(db)
                workflow_repo = WorkflowRunRepository(db)

                # Removed verbose debug log: checking_stage_state
                stage_state = stage_state_repo.get_by_workflow_and_stage(
                    self.workflow_id, self.current_stage
                )
                if not stage_state:
                    # Removed verbose debug log: creating_stage_state
                    stage_state = WorkflowStageState(
                        workflow_id=self.workflow_id,
                        stage_name=self.current_stage,
                        status=WorkflowRunStatus.RUNNING,
                        retry_count=1,
                        output_json=None,
                        error_message=str(error),
                        created_at=now,
                        updated_at=now,
                    )
                    stage_state_repo.create(stage_state)
                    db.flush()
                else:
                    # Removed verbose debug log: updating_stage_state
                    stage_state.retry_count = (stage_state.retry_count or 0) + 1
                    stage_state.error_message = str(error)
                    stage_state.updated_at = now
                    stage_state.status = WorkflowRunStatus.RUNNING
                    stage_state_repo.update(stage_state)
                    db.flush()
                # Extract primitive value for use outside session
                self.current_workflow_stage_id = getattr(stage_state, "id", None)

                # Removed verbose debug log: fetching_workflow_run
                workflow_run = workflow_repo.get_by_id(
                    self.workflow_id, lock_for_update=True
                )
                if workflow_run:
                    # Removed verbose debug log: updating_workflow_run
                    workflow_run.retry_count = (workflow_run.retry_count or 0) + 1
                    workflow_run.current_stage = self.current_stage
                    if hasattr(workflow_run, "updated_at"):
                        workflow_run.updated_at = now
                    db.flush()
                    # Extract values for logging while still in session
                    workflow_run_id = str(getattr(workflow_run, "id", None))
                    stage_val = getattr(workflow_run, "current_stage", None)
                    # Removed verbose debug log: workflow_run_stage_debug
                    if stage_val is not None and hasattr(stage_val, "name"):
                        workflow_run_stage = stage_val.name
                    elif stage_val is not None:
                        workflow_run_stage = str(stage_val)
                    workflow_run_retry_count = int(
                        getattr(workflow_run, "retry_count", 0) or 0
                    )
                else:
                    logger.debug("workflow_run_not_found", workflow_id=self.workflow_id)

                # Removed verbose debug log: log_values_extracted
                db.commit()
        except Exception as db_exc:
            logger.error(
                "pipeline_retry_db_error",
                workflow_id=self.workflow_id,
                stage=self.current_stage.value,
                attempt=attempt,
                error=str(error),
                db_error=str(db_exc),
                workflow_stage_state_id=self.current_workflow_stage_id,
            )
            # Do not raise, just log

        # Only log primitive values outside session context!
        logger.warning(
            "stage_retrying",
            workflow_id=self.workflow_id,
            stage=self.current_stage.value,
            attempt=attempt,
            error=str(error),
            workflow_stage_state_id=self.current_workflow_stage_id,
            workflow_run_id=workflow_run_id,
            workflow_run_stage=workflow_run_stage,
            workflow_run_retry_count=workflow_run_retry_count,
        )

    def __handle_pipeline_success(self, result: dict):
        """
        Handles all success logic for a pipeline stage:
            1. Insert or update workflow_stage_state for this stage (reset retry_count, clear error, persist output)
            2. Update workflow_run status (RUNNING or COMPLETED) and advance current_stage if not last stage
            3. Persist ARRecord updates if present in result['ar_record_update']
            4. Commit all DB changes atomically
            5. Log and raise if workflow_run is missing
            6. Log warning if ARRecord update requested but not found
            7. Robustly handle output_json serialization errors
            8. Log the final state for observability
        """
        workflow_status = None
        ar_record_updated = False
        with get_db_session() as db:
            stage_state_repo = WorkflowStageStateRepository(db)
            stage_state = stage_state_repo.get_by_workflow_and_stage(
                self.workflow_id, self.current_stage
            )
            now = datetime.now(UTC)
            # Robust output_json serialization
            try:
                output_json = json.dumps(result)
            except Exception as ser_exc:
                logger.error(
                    "output_json_serialization_failed",
                    error=str(ser_exc),
                    result_preview=str(result)[:200],
                )
                output_json = None

            if not stage_state:
                stage_state = WorkflowStageState(
                    workflow_id=self.workflow_id,
                    stage_name=self.current_stage,
                    status=WorkflowRunStatus.COMPLETED,
                    retry_count=0,
                    output_json=output_json,
                    error_message=None,
                    created_at=now,
                    updated_at=now,
                )
                stage_state_repo.create(stage_state)
            else:
                stage_state.status = WorkflowRunStatus.COMPLETED
                stage_state.retry_count = 0
                stage_state.output_json = output_json
                stage_state.error_message = None
                stage_state.updated_at = now
                stage_state_repo.update(stage_state)
            self.current_workflow_stage_id = getattr(stage_state, "id", None)

            workflow_repo = WorkflowRunRepository(db)
            workflow_run = workflow_repo.get_by_id(
                self.workflow_id, lock_for_update=True
            )
            if not workflow_run:
                logger.critical(
                    "workflow_run_missing_on_success",
                    workflow_id=self.workflow_id,
                    stage=self.current_stage.value,
                )
                db.rollback()
                raise RuntimeError(
                    f"WorkflowRun '{self.workflow_id}' not found during pipeline success handling."
                )

            if self.__is_last_stage():
                workflow_run.status = WorkflowRunStatus.COMPLETED
            else:
                workflow_run.status = WorkflowRunStatus.RUNNING
                next_stage = self._get_next_stage(self.current_stage)
                if next_stage:
                    workflow_run.current_stage = next_stage
            db.flush()
            workflow_status = workflow_run.status.name if workflow_run else None

            if self.customer_id and "ar_record_update" in result:
                ar_service = ARRecordService(db)
                ar_record = ar_service.get_record_by_customer_id(self.customer_id)
                if ar_record:
                    ar_service.update_record(ar_record.id, **result["ar_record_update"])
                    ar_record_updated = True
                else:
                    logger.warning(
                        "ar_record_update_requested_but_not_found",
                        customer_id=self.customer_id,
                        workflow_id=self.workflow_id,
                    )

            db.commit()

        logger.info(
            "stage_completed",
            workflow_id=self.workflow_id,
            stage=self.current_stage.value,
            workflow_status=workflow_status,
            ar_record_updated=ar_record_updated,
            stage_state_id=self.current_workflow_stage_id,
        )

    def run(self):
        try:
            self._execute_pipeline()
            return {
                "workflow_id": self.workflow_id,
                "current workflow stage": self.current_stage,
                "status": "SUCCESS",
                "message": "",
            }
        except Exception as exc:
            logger.critical(
                "pipeline_unexpected_error",
                workflow_id=self.workflow_id,
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            return {
                "workflow_id": self.workflow_id,
                "current workflow stage": self.current_stage,
                "status": "FAILED",
                "message": str(exc),
            }

    def _execute_pipeline(self):
        """Execute the pipeline stages sequentially with retry logic."""
        # Ensure data is available before starting (handles resume from failed stage)
        self._ensure_data_available()

        while self.current_stage:
            stage_config = AR_RECONCILIATION_PIPELINE_STAGES[self.current_stage]
            max_retries = stage_config["max_retries"]
            success = False
            for attempt in range(1, max_retries + 1):
                logger.info(
                    "stage_executing",
                    workflow_id=self.workflow_id,
                    stage=self.current_stage.value,
                    attempt=attempt,
                )
                try:
                    self.current_processed_data = self._execute_stage(
                        self.current_processed_data
                    )
                    self.__handle_pipeline_success(self.current_processed_data)
                    success = True
                    break
                except Exception as exc:
                    self.__handle_pipeline_retry(exc, attempt)
            if not success:
                self.__handle_pipeline_failure(
                    RuntimeError(
                        f"Stage '{self.current_stage.value}' failed after {max_retries} retries"
                    )
                )
                raise RuntimeError(
                    f"Stage '{self.current_stage.value}' failed after {max_retries} retries"
                )

            # Check if this was the last stage and persist final output
            next_stage = self._get_next_stage(self.current_stage)
            if next_stage is None:
                self._persist_final_output()

            self.current_stage = next_stage

    def _persist_final_output(self):
        """Persist the final pipeline output to the ProcessedRecord table."""
        if not self.customer_id:
            logger.warning(
                "cannot_persist_final_output_no_customer_id",
                workflow_id=self.workflow_id,
            )
            return

        try:
            with get_db_session() as db:
                processed_record_service = ProcessedRecordService(db)

                # Check if already persisted (idempotent)
                if processed_record_service.exists_for_workflow(self.workflow_id):
                    logger.info(
                        "processed_record_already_exists",
                        workflow_id=self.workflow_id,
                        customer_id=self.customer_id,
                    )
                    return

                processed_record_service.create_from_pipeline_output(
                    customer_id=self.customer_id,
                    workflow_id=self.workflow_id,
                    pipeline_output=self.current_processed_data,
                    processing_started_at=self.processing_started_at,
                )
                db.commit()

            logger.info(
                "pipeline_output_persisted",
                workflow_id=self.workflow_id,
                customer_id=self.customer_id,
            )
        except Exception as e:
            logger.error(
                "failed_to_persist_final_output",
                workflow_id=self.workflow_id,
                customer_id=self.customer_id,
                error=str(e),
            )
            # Don't raise - pipeline itself succeeded, just logging failed
            # The output is still in workflow_stage_state table

    def _get_next_stage(
        self, current_stage: WorkflowStageName
    ) -> WorkflowStageName | None:
        stages = list(AR_RECONCILIATION_PIPELINE_STAGES.keys())
        current_index = stages.index(current_stage)
        next_index = current_index + 1
        if next_index >= len(stages):
            return None
        return stages[next_index]

    def _execute_stage(self, data_to_process: dict) -> dict:
        stage_config = AR_RECONCILIATION_PIPELINE_STAGES.get(self.current_stage)
        if not stage_config:
            raise ValueError(f"Unknown stage: {self.current_stage}")
        handler = self._load_handler(stage_config["handler"])
        return handler(data_to_process)

    def _load_handler(self, handler_path: str):
        module_path, function_name = handler_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, function_name)


# class RunPipelineRequest(BaseModel):
#     workflow_id: str
#     customer_id: str


# class ResumePipelineRequest(BaseModel):
#     workflow_id: str
#     customer_id: str | None = None
#     stage: str  # Stage name to resume from (e.g., "NORMALIZATION", "BALANCE_COMPUTE")


# @router.post("/run", status_code=status.HTTP_200_OK)
# def run_pipeline(request: RunPipelineRequest):
#     return PipelineRunner(workflow_id=request.workflow_id, customer_id=request.customer_id).run()


# @router.post("/resume", status_code=status.HTTP_200_OK)
# def resume_pipeline(request: ResumePipelineRequest):
#     """
#     Resume a failed pipeline from a specific stage.
#     The stage's input data will be loaded from the previous stage's output stored in the database.
#     """
#     try:
#         # Convert stage string to enum
#         stage_enum = WorkflowStageName[request.stage.upper()]
#     except KeyError:
#         valid_stages = [s.name for s in WorkflowStageName]
#         return {
#             "workflow_id": request.workflow_id,
#             "status": "FAILED",
#             "message": f"Invalid stage '{request.stage}'. Valid stages: {valid_stages}",
#         }

#     return PipelineRunner(
#         workflow_id=request.workflow_id,
#         customer_id=request.customer_id,
#         stage=stage_enum
#     ).run()

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RecordSubmit(BaseModel):
    customer_id: str
    customer_name: str | None = None
    customer_balance: float | None = None
    invoice_total: float | None = None
    invoice_applied_amount: float | None = None
    invoice_exchange_rate: float | None = None
    payment_total: float | None = None
    payment_applied_amount: float | None = None
    payment_exchange_rate: float | None = None
    credit_total: float | None = None
    credit_applied_amount: float | None = None
    credit_exchange_rate: float | None = None
    adjustment_total: float | None = None
    adjustment_applied_amount: float | None = None
    adjustment_exchange_rate: float | None = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    invoice_id: str
    customer_id: str | None = None
    status: str
    current_stage: str | None = None
    retry_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StageStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: str
    stage_name: str
    status: str
    output_json: str | None = None
    error_message: str | None = None
    updated_at: datetime | None = None


class WorkflowDetailResponse(BaseModel):
    workflow: WorkflowResponse
    stages: list[StageStateResponse]


class BulkUploadResponse(BaseModel):
    total_records: int
    submitted: int
    duplicates: int
    workflow_ids: list[str]


class SubmitResponse(BaseModel):
    workflow_id: str
    status: str
    message: str


class WorkflowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    invoice_id: str
    customer_id: str | None = None
    status: str
    current_stage: str | None = None
    retry_count: int
    is_stale: bool = False
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StatsResponse(BaseModel):
    total_workflows: int
    completed: int
    failed: int
    pending: int
    running: int
    stale: int
    decisions: dict[str, int]

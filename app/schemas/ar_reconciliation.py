from app.schemas.api_base import APIBaseRequest, APIBaseResponse


class RecordSubmitRequest(APIBaseRequest):
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


class RecordSubmitResponse(APIBaseResponse):
    customer_id: str
    workflow_id: str
    workflow_status: str
    workflow_current_stage: str
    message: str

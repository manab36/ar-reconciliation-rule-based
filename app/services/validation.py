import structlog

from app.services.failure_sim import maybe_fail

logger = structlog.get_logger()


def validate_record(workflow_id: str, record_data: dict) -> dict:
    """
    Validation stage: apply business rules to ensure record integrity.

    Checks:
    - Customer ID is present
    - Invoice total is non-negative
    - Payment total is non-negative
    - Exchange rates are positive
    """
    maybe_fail()

    errors = []

    if not record_data.get("customer_id"):
        errors.append("Missing customer_id")

    invoice_total = record_data.get("invoice_total")
    if invoice_total is not None and invoice_total < 0:
        errors.append("Negative invoice_total")

    payment_total = record_data.get("payment_total")
    if payment_total is not None and payment_total < 0:
        errors.append("Negative payment_total")

    for rate_field in [
        "invoice_exchange_rate",
        "payment_exchange_rate",
        "credit_exchange_rate",
        "adjustment_exchange_rate",
    ]:
        rate = record_data.get(rate_field)
        if rate is not None and rate <= 0:
            errors.append(f"Invalid {rate_field}: {rate}")

    is_valid = len(errors) == 0

    logger.info(
        "validation_complete",
        workflow_id=workflow_id,
        is_valid=is_valid,
        error_count=len(errors),
    )

    return {
        "is_valid": is_valid,
        "errors": errors,
    }

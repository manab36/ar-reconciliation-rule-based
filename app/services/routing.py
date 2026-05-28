import structlog

from app.core.config import settings
from app.services.failure_sim import maybe_fail

logger = structlog.get_logger()


ROUTING_TABLE = {
    "MATCHED": "AUTO_APPROVED",
    "PARTIAL": "MANUAL_REVIEW",
    "OVERPAID": "FINANCE_REVIEW",
    "OUTSTANDING": "COLLECTION_QUEUE",
}


def route_decision(
    workflow_id: str, match_result: str, is_valid: bool, invoice_total: float = 0.0
) -> dict:
    """
    Decision routing stage: determine final disposition based on matching + validation.

    If validation failed, route to REJECTED.
    Otherwise, route based on match result.
    High-value invoices are flagged for priority review.
    """
    maybe_fail()

    high_value = invoice_total >= settings.HIGH_VALUE_THRESHOLD

    if not is_valid:
        decision = "REJECTED"
    elif high_value and match_result != "MATCHED":
        decision = "FINANCE_REVIEW"
    else:
        decision = ROUTING_TABLE.get(match_result, "MANUAL_REVIEW")

    logger.info(
        "routing_complete",
        workflow_id=workflow_id,
        decision=decision,
        match_result=match_result,
        is_valid=is_valid,
        high_value=high_value,
    )

    return {
        "decision": decision,
        "match_result": match_result,
        "is_valid": is_valid,
        "high_value": high_value,
    }

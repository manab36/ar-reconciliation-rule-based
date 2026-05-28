import structlog

from app.core.config import settings
from app.services.failure_sim import maybe_fail

logger = structlog.get_logger()


def match_record(workflow_id: str, record_data: dict) -> dict:
    """Compare invoice vs payment totals and classify as MATCHED/OUTSTANDING/PARTIAL/OVERPAID."""
    maybe_fail()

    invoice_total = record_data.get("invoice_total") or 0.0
    payment_total = record_data.get("payment_total") or 0.0

    # Percentage-based tolerance (e.g. 5% means within 5% of invoice is considered matched)
    tolerance = (
        (settings.MATCH_TOLERANCE_PERCENT / 100.0) * invoice_total
        if invoice_total
        else 0.01
    )

    if abs(payment_total - invoice_total) <= tolerance:
        match_result = "MATCHED"
    elif payment_total == 0:
        match_result = "OUTSTANDING"
    elif payment_total < invoice_total:
        match_result = "PARTIAL"
    else:
        match_result = "OVERPAID"

    logger.info(
        "matching_complete",
        workflow_id=workflow_id,
        match_result=match_result,
        invoice_total=invoice_total,
        payment_total=payment_total,
    )

    return {
        "match_result": match_result,
        "invoice_total": invoice_total,
        "payment_total": payment_total,
        "difference": round(payment_total - invoice_total, 2),
    }

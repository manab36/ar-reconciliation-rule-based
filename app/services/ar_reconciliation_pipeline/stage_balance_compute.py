"""
Stage 3: Balance Computation

Purpose: Generate calculated values from normalized transactions.

Calculations:
- invoice_outstanding = (Invoice Total - Invoice applied amount) * Invoice exchange rate
- payment_unapplied = (Payment Total - Payment applied amount) * Payment exchange rate
- credit_available = (Credit Total - Credit applied amount) * Credit exchange rate
- adjustment_remaining = (Adjustment Total - Adjustment applied amount) * Adjustment exchange rate

Output: customer_balance_snapshot

Includes random failure simulation for testing retry logic.
"""

from typing import Any

from app.services.ar_reconciliation_pipeline.failure_utils import maybe_fail


def _compute_balance_component(
    total: float, applied: float, exchange_rate: float
) -> float:
    """
    Calculate the remaining/outstanding amount.

    Formula: (Total - Applied Amount) * Exchange Rate
    """
    return round((total - applied) * exchange_rate, 2)


def _compute_customer_balance(transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Compute all balance components for a single customer transaction.
    """
    # Extract values with defaults
    invoice_total = transaction.get("Invoice Total", 0.0)
    invoice_applied = transaction.get("Invoice applied amount", 0.0)
    invoice_rate = transaction.get("Invoice exchange rate", 1.0)

    payment_total = transaction.get("Payment Total", 0.0)
    payment_applied = transaction.get("Payment applied amount", 0.0)
    payment_rate = transaction.get("Payment exchange rate", 1.0)

    credit_total = transaction.get("Credit Total", 0.0)
    credit_applied = transaction.get("Credit applied amount", 0.0)
    credit_rate = transaction.get("Credit exchange rate", 1.0)

    adjustment_total = transaction.get("Adjustment Total", 0.0)
    adjustment_applied = transaction.get("Adjustment applied amount", 0.0)
    adjustment_rate = transaction.get("Adjustment exchange rate", 1.0)

    # Calculate balance components
    invoice_outstanding = _compute_balance_component(
        invoice_total, invoice_applied, invoice_rate
    )
    payment_unapplied = _compute_balance_component(
        payment_total, payment_applied, payment_rate
    )
    credit_available = _compute_balance_component(
        credit_total, credit_applied, credit_rate
    )
    adjustment_remaining = _compute_balance_component(
        adjustment_total, adjustment_applied, adjustment_rate
    )

    # Build result preserving original data plus computed values
    result = dict(transaction)
    result.update(
        {
            "invoice_outstanding": invoice_outstanding,
            "payment_unapplied": payment_unapplied,
            "credit_available": credit_available,
            "adjustment_remaining": adjustment_remaining,
            "_balance_computed": True,
        }
    )

    return result


def execute(data: dict[str, Any]) -> dict[str, Any]:
    """
    Balance Computation stage - calculate outstanding/unapplied amounts.

    Args:
        data: Dict containing "normalized_transactions" from normalization stage

    Returns:
        Dict containing "customer_balance_snapshot" list
    """
    # Simulate random failure for retry testing
    maybe_fail("BALANCE_COMPUTE")

    transactions = data.get("normalized_transactions", [])

    if not transactions:
        return {
            "customer_balance_snapshot": [],
            "balance_summary": {
                "total_records": 0,
                "total_invoice_outstanding": 0.0,
                "total_payment_unapplied": 0.0,
                "total_credit_available": 0.0,
                "total_adjustment_remaining": 0.0,
            },
            # Pass through normalization summary
            "normalization_summary": data.get("normalization_summary", {}),
        }

    balance_snapshots = []
    totals = {
        "invoice_outstanding": 0.0,
        "payment_unapplied": 0.0,
        "credit_available": 0.0,
        "adjustment_remaining": 0.0,
    }

    for transaction in transactions:
        computed = _compute_customer_balance(transaction)
        balance_snapshots.append(computed)

        # Accumulate totals
        totals["invoice_outstanding"] += computed["invoice_outstanding"]
        totals["payment_unapplied"] += computed["payment_unapplied"]
        totals["credit_available"] += computed["credit_available"]
        totals["adjustment_remaining"] += computed["adjustment_remaining"]

    return {
        "customer_balance_snapshot": balance_snapshots,
        "balance_summary": {
            "total_records": len(balance_snapshots),
            "total_invoice_outstanding": round(totals["invoice_outstanding"], 2),
            "total_payment_unapplied": round(totals["payment_unapplied"], 2),
            "total_credit_available": round(totals["credit_available"], 2),
            "total_adjustment_remaining": round(totals["adjustment_remaining"], 2),
        },
        # Pass through normalization summary
        "normalization_summary": data.get("normalization_summary", {}),
    }

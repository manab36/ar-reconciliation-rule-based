"""
Stage 4: Reconciliation

Purpose: Calculate expected balance and difference from customer balance.

Calculations:
- expected_balance = invoice_outstanding - payment_unapplied - credit_available - adjustment_remaining
- difference = customer_balance - expected_balance

Output: reconciliation_result

Includes random failure simulation for testing retry logic.
"""

from typing import Any

from app.services.ar_reconciliation_pipeline.failure_utils import maybe_fail


def _reconcile_customer(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Reconcile a single customer's balance.
    """
    # Get computed balance components
    invoice_outstanding = snapshot.get("invoice_outstanding", 0.0)
    payment_unapplied = snapshot.get("payment_unapplied", 0.0)
    credit_available = snapshot.get("credit_available", 0.0)
    adjustment_remaining = snapshot.get("adjustment_remaining", 0.0)

    # Get customer's reported balance
    customer_balance = snapshot.get("Customer Balance", 0.0)

    # Calculate expected balance
    # expected_balance = what customer SHOULD owe
    # = outstanding invoices - unapplied payments - available credits - remaining adjustments
    expected_balance = round(
        invoice_outstanding
        - payment_unapplied
        - credit_available
        - adjustment_remaining,
        2,
    )

    # Calculate difference
    # Positive difference = customer balance is higher than expected (they think they owe more)
    # Negative difference = customer balance is lower than expected (they think they owe less)
    difference = round(customer_balance - expected_balance, 2)

    # Build result preserving original data plus reconciliation values
    result = dict(snapshot)
    result.update(
        {
            "expected_balance": expected_balance,
            "difference": difference,
            "customer_balance": customer_balance,
            "_reconciled": True,
        }
    )

    return result


def execute(data: dict[str, Any]) -> dict[str, Any]:
    """
    Reconciliation stage - calculate expected balance and differences.

    Args:
        data: Dict containing "customer_balance_snapshot" from balance compute stage

    Returns:
        Dict containing "reconciliation_result" list
    """
    # Simulate random failure for retry testing
    maybe_fail("RECONCILIATION")

    snapshots = data.get("customer_balance_snapshot", [])

    if not snapshots:
        return {
            "reconciliation_result": [],
            "reconciliation_summary": {
                "total_records": 0,
                "total_expected_balance": 0.0,
                "total_difference": 0.0,
                "records_with_difference": 0,
            },
            # Pass through previous summaries
            "balance_summary": data.get("balance_summary", {}),
            "normalization_summary": data.get("normalization_summary", {}),
        }

    reconciliation_results = []
    total_expected = 0.0
    total_difference = 0.0
    records_with_difference = 0

    for snapshot in snapshots:
        reconciled = _reconcile_customer(snapshot)
        reconciliation_results.append(reconciled)

        total_expected += reconciled["expected_balance"]
        total_difference += abs(reconciled["difference"])

        # Count records with non-zero difference (using small threshold for float comparison)
        if abs(reconciled["difference"]) > 0.01:
            records_with_difference += 1

    return {
        "reconciliation_result": reconciliation_results,
        "reconciliation_summary": {
            "total_records": len(reconciliation_results),
            "total_expected_balance": round(total_expected, 2),
            "total_difference": round(total_difference, 2),
            "records_with_difference": records_with_difference,
        },
        # Pass through previous summaries
        "balance_summary": data.get("balance_summary", {}),
        "normalization_summary": data.get("normalization_summary", {}),
    }

"""
Stage 5: Validation Rules

Purpose: Run business rules against reconciliation results.

Rules:
- Rule A: abs(difference) within tolerance (absolute floor OR % of expected) -> MATCH
- Rule B: customer_balance < expected_balance (beyond tolerance) -> OVERPAID
- Rule C: payment_unapplied > 0 -> UNAPPLIED_PAYMENT
- Rule D: credit_available > 0 -> UNAPPLIED_CREDIT
- Rule E: customer_balance > expected_balance (beyond tolerance) -> UNDERPAID

Output: validation_result

Includes random failure simulation for testing retry logic.
"""

from enum import StrEnum
from typing import Any

from app.core.config import settings
from app.services.ar_reconciliation_pipeline.failure_utils import maybe_fail


class ValidationRule(StrEnum):
    MATCH = "MATCH"
    OVERPAID = "OVERPAID"
    UNDERPAID = "UNDERPAID"
    UNAPPLIED_PAYMENT = "UNAPPLIED_PAYMENT"
    UNAPPLIED_CREDIT = "UNAPPLIED_CREDIT"


# Absolute floor tolerance (handles zero/near-zero expected balances and float noise)
MATCH_THRESHOLD = 0.01


def _match_tolerance(expected_balance: float) -> float:
    """
    Effective tolerance for a record = max(absolute floor, % of |expected_balance|).
    """
    pct_tolerance = abs(expected_balance) * (settings.MATCH_TOLERANCE_PERCENT / 100.0)
    return max(MATCH_THRESHOLD, pct_tolerance)


def _apply_rule_a(record: dict[str, Any]) -> dict[str, Any]:
    """
    Rule A: Check if difference is within tolerance (MATCH).
    Tolerance = max(MATCH_THRESHOLD, MATCH_TOLERANCE_PERCENT% of expected_balance).
    """
    difference = record.get("difference", 0.0)
    expected_balance = record.get("expected_balance", 0.0)
    tolerance = _match_tolerance(expected_balance)
    is_match = abs(difference) <= tolerance

    return {
        "rule_id": "A",
        "rule_name": "Balance Match Check",
        "triggered": is_match,
        "result": ValidationRule.MATCH if is_match else None,
        "details": (
            f"Difference: {difference}, Tolerance: {round(tolerance, 4)} "
            f"(pct={settings.MATCH_TOLERANCE_PERCENT}%, floor={MATCH_THRESHOLD})"
        ),
    }


def _apply_rule_b(record: dict[str, Any]) -> dict[str, Any]:
    """
    Rule B: Check if customer balance is less than expected (OVERPAID).
    Customer has paid more than they owe.
    """
    customer_balance = record.get("customer_balance", 0.0)
    expected_balance = record.get("expected_balance", 0.0)
    tolerance = _match_tolerance(expected_balance)

    # Customer owes less than expected (beyond tolerance) = they've overpaid
    is_overpaid = customer_balance < (expected_balance - tolerance)

    return {
        "rule_id": "B",
        "rule_name": "Overpayment Check",
        "triggered": is_overpaid,
        "result": ValidationRule.OVERPAID if is_overpaid else None,
        "details": f"Customer Balance: {customer_balance}, Expected: {expected_balance}",
    }


def _apply_rule_c(record: dict[str, Any]) -> dict[str, Any]:
    """
    Rule C: Check if there are unapplied payments.
    """
    payment_unapplied = record.get("payment_unapplied", 0.0)
    has_unapplied = payment_unapplied > MATCH_THRESHOLD

    return {
        "rule_id": "C",
        "rule_name": "Unapplied Payment Check",
        "triggered": has_unapplied,
        "result": ValidationRule.UNAPPLIED_PAYMENT if has_unapplied else None,
        "details": f"Unapplied Payment: {payment_unapplied}",
    }


def _apply_rule_d(record: dict[str, Any]) -> dict[str, Any]:
    """
    Rule D: Check if there are available credits.
    """
    credit_available = record.get("credit_available", 0.0)
    has_credit = credit_available > MATCH_THRESHOLD

    return {
        "rule_id": "D",
        "rule_name": "Unapplied Credit Check",
        "triggered": has_credit,
        "result": ValidationRule.UNAPPLIED_CREDIT if has_credit else None,
        "details": f"Available Credit: {credit_available}",
    }


def _apply_underpaid_rule(record: dict[str, Any]) -> dict[str, Any]:
    """
    Additional Rule: Check if customer balance is greater than expected (UNDERPAID).
    Customer owes more than expected.
    """
    customer_balance = record.get("customer_balance", 0.0)
    expected_balance = record.get("expected_balance", 0.0)
    tolerance = _match_tolerance(expected_balance)

    is_underpaid = customer_balance > (expected_balance + tolerance)

    return {
        "rule_id": "E",
        "rule_name": "Underpayment Check",
        "triggered": is_underpaid,
        "result": ValidationRule.UNDERPAID if is_underpaid else None,
        "details": f"Customer Balance: {customer_balance}, Expected: {expected_balance}",
    }


def _validate_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Apply all validation rules to a single record.
    """
    # Apply all rules
    rule_results = [
        _apply_rule_a(record),
        _apply_rule_b(record),
        _apply_rule_c(record),
        _apply_rule_d(record),
        _apply_underpaid_rule(record),
    ]

    # Collect triggered rules
    triggered_rules = [r for r in rule_results if r["triggered"]]

    # Build result preserving original data
    result = dict(record)
    result.update(
        {
            "rule_results": rule_results,
            "triggered_rules": triggered_rules,
            "rules_triggered_count": len(triggered_rules),
            "_validated": True,
        }
    )

    return result


def execute(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validation Rules stage - apply business rules to reconciliation results.

    Args:
        data: Dict containing "reconciliation_result" from reconciliation stage

    Returns:
        Dict containing "validation_result" list
    """
    # Simulate random failure for retry testing
    maybe_fail("VALIDATION_RULES")

    reconciliation_results = data.get("reconciliation_result", [])

    if not reconciliation_results:
        return {
            "validation_result": [],
            "validation_summary": {
                "total_records": 0,
                "matched_count": 0,
                "overpaid_count": 0,
                "underpaid_count": 0,
                "unapplied_payment_count": 0,
                "unapplied_credit_count": 0,
            },
            # Pass through previous summaries
            "reconciliation_summary": data.get("reconciliation_summary", {}),
            "balance_summary": data.get("balance_summary", {}),
            "normalization_summary": data.get("normalization_summary", {}),
        }

    validation_results = []
    counts = {
        "matched": 0,
        "overpaid": 0,
        "underpaid": 0,
        "unapplied_payment": 0,
        "unapplied_credit": 0,
    }

    for record in reconciliation_results:
        validated = _validate_record(record)
        validation_results.append(validated)

        # Count by rule results
        for rule in validated["triggered_rules"]:
            if rule["result"] == ValidationRule.MATCH:
                counts["matched"] += 1
            elif rule["result"] == ValidationRule.OVERPAID:
                counts["overpaid"] += 1
            elif rule["result"] == ValidationRule.UNDERPAID:
                counts["underpaid"] += 1
            elif rule["result"] == ValidationRule.UNAPPLIED_PAYMENT:
                counts["unapplied_payment"] += 1
            elif rule["result"] == ValidationRule.UNAPPLIED_CREDIT:
                counts["unapplied_credit"] += 1

    return {
        "validation_result": validation_results,
        "validation_summary": {
            "total_records": len(validation_results),
            "matched_count": counts["matched"],
            "overpaid_count": counts["overpaid"],
            "underpaid_count": counts["underpaid"],
            "unapplied_payment_count": counts["unapplied_payment"],
            "unapplied_credit_count": counts["unapplied_credit"],
        },
        # Pass through previous summaries
        "reconciliation_summary": data.get("reconciliation_summary", {}),
        "balance_summary": data.get("balance_summary", {}),
        "normalization_summary": data.get("normalization_summary", {}),
    }

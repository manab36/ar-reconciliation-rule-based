"""
Stage 6: Verdict Generation

Purpose: Combine all rule outcomes to generate final verdict for each customer.

Output example:
{
    customer_id: "CUST-001",
    verdict: "OVERPAID",
    confidence: 100
}

Output: reconciliation_verdict
"""

from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    MATCH = "MATCH"
    OVERPAID = "OVERPAID"
    UNDERPAID = "UNDERPAID"
    UNAPPLIED_PAYMENT = "UNAPPLIED_PAYMENT"
    UNAPPLIED_CREDIT = "UNAPPLIED_CREDIT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


# Priority order for verdicts (higher priority = more severe issue)
VERDICT_PRIORITY = {
    "MATCH": 0,
    "UNAPPLIED_CREDIT": 1,
    "UNAPPLIED_PAYMENT": 2,
    "OVERPAID": 3,
    "UNDERPAID": 4,
    "MANUAL_REVIEW": 5,
}


def _calculate_confidence(triggered_rules: list[dict[str, Any]], verdict: str) -> int:
    """
    Calculate confidence score for the verdict.

    - 100% if only one rule triggered and it matches the verdict
    - Lower confidence if multiple conflicting rules
    """
    if not triggered_rules:
        return 0

    # If only MATCH rule triggered, 100% confidence
    if len(triggered_rules) == 1 and triggered_rules[0].get("result") == verdict:
        return 100

    # If MATCH is triggered along with other rules, it means
    # the balance matches but there are other issues
    match_triggered = any(r.get("result") == "MATCH" for r in triggered_rules)

    if match_triggered:
        # High confidence - balance matches but secondary issues exist
        return 90

    # Multiple rules triggered - confidence based on number of issues
    num_rules = len(triggered_rules)
    # Confidence decreases as more rules are triggered
    confidence_map = {1: 100, 2: 85, 3: 70}
    return confidence_map.get(num_rules, 50)  # Default: Many issues = lower confidence


def _determine_verdict(validated_record: dict[str, Any]) -> dict[str, Any]:
    """
    Determine the final verdict for a customer based on triggered rules.
    """
    customer_id = validated_record.get(
        "Customer ID", validated_record.get("customer_id", "UNKNOWN")
    )
    triggered_rules = validated_record.get("triggered_rules", [])

    if not triggered_rules:
        # No rules triggered - needs manual review
        return {
            "customer_id": customer_id,
            "verdict": Verdict.MANUAL_REVIEW,
            "confidence": 0,
            "triggered_rules_summary": [],
            "reason": "No validation rules triggered",
        }

    # Get all triggered rule results
    rule_results = [r.get("result") for r in triggered_rules if r.get("result")]

    # Check for MATCH first
    if Verdict.MATCH in rule_results:
        # If MATCH and no other balance issues, it's a clean match
        non_match_rules = [r for r in rule_results if r != Verdict.MATCH]

        if not non_match_rules:
            return {
                "customer_id": customer_id,
                "verdict": Verdict.MATCH,
                "confidence": 100,
                "triggered_rules_summary": rule_results,
                "reason": "Balance matches within tolerance",
            }
        else:
            # Balance matches but has secondary issues
            # Return the highest priority secondary issue
            highest_priority_rule = max(
                non_match_rules, key=lambda x: VERDICT_PRIORITY.get(x, 0)
            )
            return {
                "customer_id": customer_id,
                "verdict": highest_priority_rule,
                "confidence": _calculate_confidence(
                    triggered_rules, highest_priority_rule
                ),
                "triggered_rules_summary": rule_results,
                "reason": f"Balance matches but has {highest_priority_rule.lower().replace('_', ' ')}",
            }

    # No MATCH - determine primary verdict by priority
    highest_priority_rule = max(rule_results, key=lambda x: VERDICT_PRIORITY.get(x, 0))

    return {
        "customer_id": customer_id,
        "verdict": highest_priority_rule,
        "confidence": _calculate_confidence(triggered_rules, highest_priority_rule),
        "triggered_rules_summary": rule_results,
        "reason": f"Primary issue: {highest_priority_rule.lower().replace('_', ' ')}",
    }


def _generate_customer_verdict(validated_record: dict[str, Any]) -> dict[str, Any]:
    """
    Generate complete verdict record for a customer.
    """
    verdict_info = _determine_verdict(validated_record)

    # Include additional context from the validated record
    result = {
        **verdict_info,
        "customer_name": validated_record.get(
            "Customer Name", validated_record.get("customer_name", "Unknown")
        ),
        "customer_balance": validated_record.get("customer_balance", 0.0),
        "expected_balance": validated_record.get("expected_balance", 0.0),
        "difference": validated_record.get("difference", 0.0),
        "invoice_outstanding": validated_record.get("invoice_outstanding", 0.0),
        "payment_unapplied": validated_record.get("payment_unapplied", 0.0),
        "credit_available": validated_record.get("credit_available", 0.0),
        "adjustment_remaining": validated_record.get("adjustment_remaining", 0.0),
    }

    return result


def execute(data: dict[str, Any]) -> dict[str, Any]:
    """
    Verdict Generation stage - combine rule outcomes into final verdicts.

    Args:
        data: Dict containing "validation_result" from validation stage

    Returns:
        Dict containing "reconciliation_verdict" list
    """
    validation_results = data.get("validation_result", [])

    if not validation_results:
        return {
            "reconciliation_verdict": [],
            "verdict_summary": {
                "total_customers": 0,
                "matched": 0,
                "overpaid": 0,
                "underpaid": 0,
                "manual_review": 0,
                "average_confidence": 0,
            },
            # Pass through previous summaries
            "validation_summary": data.get("validation_summary", {}),
            "reconciliation_summary": data.get("reconciliation_summary", {}),
            "balance_summary": data.get("balance_summary", {}),
            "normalization_summary": data.get("normalization_summary", {}),
        }

    verdicts = []
    counts = {
        "matched": 0,
        "overpaid": 0,
        "underpaid": 0,
        "manual_review": 0,
        "unapplied_payment": 0,
        "unapplied_credit": 0,
    }
    total_confidence = 0

    for record in validation_results:
        verdict = _generate_customer_verdict(record)
        verdicts.append(verdict)

        # Count by verdict
        verdict_type = verdict["verdict"]
        if verdict_type == Verdict.MATCH:
            counts["matched"] += 1
        elif verdict_type == Verdict.OVERPAID:
            counts["overpaid"] += 1
        elif verdict_type == Verdict.UNDERPAID:
            counts["underpaid"] += 1
        elif verdict_type == Verdict.MANUAL_REVIEW:
            counts["manual_review"] += 1
        elif verdict_type == Verdict.UNAPPLIED_PAYMENT:
            counts["unapplied_payment"] += 1
        elif verdict_type == Verdict.UNAPPLIED_CREDIT:
            counts["unapplied_credit"] += 1

        total_confidence += verdict["confidence"]

    avg_confidence = round(total_confidence / len(verdicts), 2) if verdicts else 0

    return {
        "reconciliation_verdict": verdicts,
        "verdict_summary": {
            "total_customers": len(verdicts),
            "matched": counts["matched"],
            "overpaid": counts["overpaid"],
            "underpaid": counts["underpaid"],
            "unapplied_payment": counts["unapplied_payment"],
            "unapplied_credit": counts["unapplied_credit"],
            "manual_review": counts["manual_review"],
            "average_confidence": avg_confidence,
        },
        # Pass through previous summaries
        "validation_summary": data.get("validation_summary", {}),
        "reconciliation_summary": data.get("reconciliation_summary", {}),
        "balance_summary": data.get("balance_summary", {}),
        "normalization_summary": data.get("normalization_summary", {}),
    }

"""
Stage 7: Reporting

Purpose: Generate final reports from reconciliation verdicts.

Outputs:
1. Summary Report:
   - Total Customers
   - Matched
   - Overpaid
   - Underpaid
   - Manual Review

2. Exception Report:
   - Only failed/exception customers

3. Audit Report:
   - Who ran
   - When ran
   - Input file
   - Version of rules

Includes random failure simulation for testing retry logic.
"""

from datetime import UTC, datetime
from typing import Any

from app.services.ar_reconciliation_pipeline.failure_utils import maybe_fail

# Rule version for audit tracking
RULES_VERSION = "1.0.0"


def _generate_summary_report(
    verdicts: list[dict[str, Any]], verdict_summary: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate summary report with totals.
    """
    return {
        "report_type": "SUMMARY",
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": {
            "total_customers": verdict_summary.get("total_customers", len(verdicts)),
            "matched": verdict_summary.get("matched", 0),
            "overpaid": verdict_summary.get("overpaid", 0),
            "underpaid": verdict_summary.get("underpaid", 0),
            "unapplied_payment": verdict_summary.get("unapplied_payment", 0),
            "unapplied_credit": verdict_summary.get("unapplied_credit", 0),
            "manual_review": verdict_summary.get("manual_review", 0),
            "average_confidence": verdict_summary.get("average_confidence", 0),
        },
        "percentages": _calculate_percentages(verdict_summary),
    }


def _calculate_percentages(summary: dict[str, Any]) -> dict[str, float]:
    """
    Calculate percentage breakdown.
    """
    total = summary.get("total_customers", 0)
    if total == 0:
        return {
            "matched_pct": 0,
            "overpaid_pct": 0,
            "underpaid_pct": 0,
            "exception_pct": 0,
        }

    matched = summary.get("matched", 0)
    overpaid = summary.get("overpaid", 0)
    underpaid = summary.get("underpaid", 0)
    exceptions = total - matched

    return {
        "matched_pct": round((matched / total) * 100, 2),
        "overpaid_pct": round((overpaid / total) * 100, 2),
        "underpaid_pct": round((underpaid / total) * 100, 2),
        "exception_pct": round((exceptions / total) * 100, 2),
    }


def _generate_exception_report(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Generate exception report containing only failed customers.
    """
    exceptions = []

    for verdict in verdicts:
        verdict_type = verdict.get("verdict", "")

        # Include all non-MATCH verdicts as exceptions
        if verdict_type != "MATCH":
            exceptions.append(
                {
                    "customer_id": verdict.get("customer_id"),
                    "customer_name": verdict.get("customer_name"),
                    "verdict": verdict_type,
                    "confidence": verdict.get("confidence", 0),
                    "reason": verdict.get("reason", ""),
                    "customer_balance": verdict.get("customer_balance", 0),
                    "expected_balance": verdict.get("expected_balance", 0),
                    "difference": verdict.get("difference", 0),
                    "triggered_rules": verdict.get("triggered_rules_summary", []),
                }
            )

    # Sort by absolute difference (largest discrepancies first)
    exceptions.sort(key=lambda x: abs(x.get("difference", 0)), reverse=True)

    return {
        "report_type": "EXCEPTION",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_exceptions": len(exceptions),
        "exceptions": exceptions,
    }


def _generate_audit_report(
    run_info: dict[str, Any],
    normalization_summary: dict[str, Any],
    balance_summary: dict[str, Any],
    reconciliation_summary: dict[str, Any],
    validation_summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Generate audit report with execution metadata.
    """
    return {
        "report_type": "AUDIT",
        "generated_at": datetime.now(UTC).isoformat(),
        "execution_info": {
            "run_by": run_info.get("run_by", "system"),
            "run_at": run_info.get("run_at", datetime.now(UTC).isoformat()),
            "input_file": run_info.get("input_file", "unknown"),
            "workflow_id": run_info.get("workflow_id", "unknown"),
        },
        "rules_info": {
            "version": RULES_VERSION,
            "rules_applied": [
                {
                    "id": "A",
                    "name": "Balance Match Check",
                    "description": "abs(difference) < 0.01 -> MATCH",
                },
                {
                    "id": "B",
                    "name": "Overpayment Check",
                    "description": "customer_balance < expected_balance -> OVERPAID",
                },
                {
                    "id": "C",
                    "name": "Unapplied Payment Check",
                    "description": "payment_unapplied > 0 -> UNAPPLIED_PAYMENT",
                },
                {
                    "id": "D",
                    "name": "Unapplied Credit Check",
                    "description": "credit_available > 0 -> UNAPPLIED_CREDIT",
                },
                {
                    "id": "E",
                    "name": "Underpayment Check",
                    "description": "customer_balance > expected_balance -> UNDERPAID",
                },
            ],
        },
        "pipeline_stages": {
            "normalization": normalization_summary,
            "balance_compute": balance_summary,
            "reconciliation": reconciliation_summary,
            "validation": validation_summary,
        },
    }


def execute(data: dict[str, Any]) -> dict[str, Any]:
    """
    Reporting stage - generate final reports.

    Args:
        data: Dict containing "reconciliation_verdict" and all previous summaries

    Returns:
        Dict containing all reports (summary, exception, audit)
    """
    # Simulate random failure for retry testing
    maybe_fail("REPORTING")

    verdicts = data.get("reconciliation_verdict", [])
    verdict_summary = data.get("verdict_summary", {})

    # Get previous stage summaries for audit
    normalization_summary = data.get("normalization_summary", {})
    balance_summary = data.get("balance_summary", {})
    reconciliation_summary = data.get("reconciliation_summary", {})
    validation_summary = data.get("validation_summary", {})

    # Get run info if provided
    run_info = data.get("run_info", {})

    # Generate all reports
    summary_report = _generate_summary_report(verdicts, verdict_summary)
    exception_report = _generate_exception_report(verdicts)
    audit_report = _generate_audit_report(
        run_info,
        normalization_summary,
        balance_summary,
        reconciliation_summary,
        validation_summary,
    )

    return {
        "summary_report": summary_report,
        "exception_report": exception_report,
        "audit_report": audit_report,
        "reconciliation_verdict": verdicts,
        "final_status": {
            "success": True,
            "total_processed": len(verdicts),
            "total_exceptions": exception_report["total_exceptions"],
            "completion_time": datetime.now(UTC).isoformat(),
        },
    }

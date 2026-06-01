"""
Stage 2: Normalization

Purpose: Clean data before calculations.

Actions:
- Convert string numbers like "3486.58" to float 3486.58
- Handle NULL, '', 'N/A' by converting to 0
- Validate exchange rates (rate > 0)

Output: normalized_transactions

Includes random failure simulation for testing retry logic.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.ar_reconciliation_pipeline.failure_utils import maybe_fail

# Fields that should be converted to numeric values
NUMERIC_FIELDS = [
    "Customer Balance",
    "Invoice Total",
    "Invoice applied amount",
    "Invoice exchange rate",
    "Payment Total",
    "Payment applied amount",
    "Payment exchange rate",
    "Credit Total",
    "Credit applied amount",
    "Credit exchange rate",
    "Adjustment Total",
    "Adjustment applied amount",
    "Adjustment exchange rate",
]

# Fields that represent exchange rates (must be > 0)
EXCHANGE_RATE_FIELDS = [
    "Invoice exchange rate",
    "Payment exchange rate",
    "Credit exchange rate",
    "Adjustment exchange rate",
]

# Values to treat as zero/null
NULL_VALUES = {None, "", "NULL", "null", "N/A", "n/a", "NA", "na", "None", "none"}


def _normalize_value(value: Any) -> float:
    """
    Convert a value to float.

    - String numbers -> float
    - NULL/empty/'N/A' -> 0
    - Already numeric -> float
    """
    # Handle null-like values
    if value in NULL_VALUES:
        return 0.0

    # Handle string values
    if isinstance(value, str):
        value = value.strip()
        if value in NULL_VALUES or value == "":
            return 0.0
        try:
            return float(value)
        except (ValueError, InvalidOperation):
            return 0.0

    # Handle numeric values
    if isinstance(value, (int, float, Decimal)):
        return float(value)

    # Default to 0 for unknown types
    return 0.0


def _validate_exchange_rate(
    rate: float, field_name: str, customer_id: str
) -> dict[str, Any]:
    """
    Validate that exchange rate is positive.

    Returns validation result with any warnings.
    """
    if rate <= 0:
        return {
            "valid": False,
            "warning": f"Invalid exchange rate for {field_name}: {rate} (must be > 0)",
            "customer_id": customer_id,
            "corrected_value": 1.0,  # Default to 1.0 for invalid rates
        }
    return {"valid": True}


def _normalize_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a single transaction record.
    """
    normalized = {}
    warnings = []
    customer_id = transaction.get(
        "Customer ID", transaction.get("customer_id", "UNKNOWN")
    )

    for key, value in transaction.items():
        if key in NUMERIC_FIELDS:
            normalized_value = _normalize_value(value)

            # Validate exchange rates
            if key in EXCHANGE_RATE_FIELDS:
                validation = _validate_exchange_rate(normalized_value, key, customer_id)
                if not validation["valid"]:
                    warnings.append(validation["warning"])
                    normalized_value = validation["corrected_value"]

            normalized[key] = normalized_value
        else:
            # Keep non-numeric fields as-is
            normalized[key] = value

    # Add normalization metadata
    normalized["_normalization_warnings"] = warnings
    normalized["_normalized"] = True

    return normalized


def execute(data: dict[str, Any]) -> dict[str, Any]:
    """
    Normalization stage - clean and validate data.

    Args:
        data: Dict containing "transactions" list from ingestion stage

    Returns:
        Dict containing "normalized_transactions" list
    """
    # Simulate random failure for retry testing
    maybe_fail("NORMALIZATION")

    transactions = data.get("transactions", [])

    if not transactions:
        return {
            "normalized_transactions": [],
            "normalization_summary": {
                "total_records": 0,
                "records_with_warnings": 0,
                "total_warnings": 0,
            },
        }

    normalized_transactions = []
    total_warnings = 0
    records_with_warnings = 0

    for transaction in transactions:
        normalized = _normalize_transaction(transaction)
        normalized_transactions.append(normalized)

        if normalized.get("_normalization_warnings"):
            records_with_warnings += 1
            total_warnings += len(normalized["_normalization_warnings"])

    return {
        "normalized_transactions": normalized_transactions,
        "normalization_summary": {
            "total_records": len(normalized_transactions),
            "records_with_warnings": records_with_warnings,
            "total_warnings": total_warnings,
        },
    }

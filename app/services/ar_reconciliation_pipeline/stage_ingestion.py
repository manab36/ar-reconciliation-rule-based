"""
Stage 1: Ingestion

Purpose: Accept input data and pass through.
For now, this stage just returns the input data unchanged.
Includes random failure simulation for testing retry logic.
"""

from typing import Any

from app.services.ar_reconciliation_pipeline.failure_utils import maybe_fail


def execute(data: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """
    Ingestion stage - accepts JSON data and returns it unchanged.

    Args:
        data: Input data (single record or list of records)

    Returns:
        Dict containing the ingested transactions
    """
    # Simulate random failure for retry testing
    maybe_fail("INGESTION")

    # If data is already a dict with transactions key, pass through
    if isinstance(data, dict) and "transactions" in data:
        return data

    # If data is a single record (dict), wrap it in a list
    if isinstance(data, dict):
        return {"transactions": [data]}

    # If data is a list of records
    if isinstance(data, list):
        return {"transactions": data}

    # Default: return as-is wrapped in transactions
    return {"transactions": [data] if data else []}

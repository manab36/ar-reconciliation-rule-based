import csv
import hashlib
import json
import uuid

import structlog
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db_session
from app.services.failure_sim import maybe_fail
from database_ops.model import ARRecord, ProcessedRecord

logger = structlog.get_logger()


def parse_csv_records(file_path: str) -> list[dict]:
    """Parse the ERP export CSV into a list of record dicts."""
    records = []
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(
                {
                    "customer_id": row["Customer ID"],
                    "customer_name": row["Customer Name"],
                    "customer_balance": float(row["Customer Balance"])
                    if row["Customer Balance"]
                    else None,
                    "invoice_total": float(row["Invoice Total"])
                    if row["Invoice Total"]
                    else None,
                    "invoice_applied_amount": float(row["Invoice applied amount"])
                    if row["Invoice applied amount"]
                    else None,
                    "invoice_exchange_rate": float(row["Invoice exchange rate"])
                    if row["Invoice exchange rate"]
                    else None,
                    "payment_total": float(row["Payment Total"])
                    if row["Payment Total"]
                    else None,
                    "payment_applied_amount": float(row["Payment applied amount"])
                    if row["Payment applied amount"]
                    else None,
                    "payment_exchange_rate": float(row["Payment exchange rate"])
                    if row["Payment exchange rate"]
                    else None,
                    "credit_total": float(row["Credit Total"])
                    if row["Credit Total"]
                    else None,
                    "credit_applied_amount": float(row["Credit applied amount"])
                    if row["Credit applied amount"]
                    else None,
                    "credit_exchange_rate": float(row["Credit exchange rate"])
                    if row["Credit exchange rate"]
                    else None,
                    "adjustment_total": float(row["Adjustment Total"])
                    if row["Adjustment Total"]
                    else None,
                    "adjustment_applied_amount": float(row["Adjustment applied amount"])
                    if row["Adjustment applied amount"]
                    else None,
                    "adjustment_exchange_rate": float(row["Adjustment exchange rate"])
                    if row["Adjustment exchange rate"]
                    else None,
                }
            )
    return records

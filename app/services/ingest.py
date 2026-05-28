import csv
import hashlib
import json
import uuid

import structlog

from app.core.database import SessionLocal
from app.models.record import ARRecord, ProcessedRecord
from app.services.failure_sim import maybe_fail

logger = structlog.get_logger()


def ingest_record(workflow_id: str, record_data: dict) -> dict:
    """
    Ingestion stage: parse and persist the raw AR record.
    Generates an idempotency key to prevent duplicate processing.
    """
    maybe_fail()

    customer_id = record_data.get("customer_id")
    idempotency_key = hashlib.sha256(
        json.dumps(record_data, sort_keys=True).encode()
    ).hexdigest()

    db = SessionLocal()
    try:
        # Check for duplicate
        existing = (
            db.query(ProcessedRecord).filter_by(idempotency_key=idempotency_key).first()
        )
        if existing:
            logger.info(
                "duplicate_record_skipped",
                customer_id=customer_id,
                workflow_id=workflow_id,
            )
            return {"status": "DUPLICATE", "record_id": existing.invoice_id}

        record_id = str(uuid.uuid4())
        ar_record = ARRecord(
            id=record_id,
            customer_id=customer_id,
            customer_name=record_data.get("customer_name"),
            customer_balance=record_data.get("customer_balance"),
            invoice_total=record_data.get("invoice_total"),
            invoice_applied_amount=record_data.get("invoice_applied_amount"),
            invoice_exchange_rate=record_data.get("invoice_exchange_rate"),
            payment_total=record_data.get("payment_total"),
            payment_applied_amount=record_data.get("payment_applied_amount"),
            payment_exchange_rate=record_data.get("payment_exchange_rate"),
            credit_total=record_data.get("credit_total"),
            credit_applied_amount=record_data.get("credit_applied_amount"),
            credit_exchange_rate=record_data.get("credit_exchange_rate"),
            adjustment_total=record_data.get("adjustment_total"),
            adjustment_applied_amount=record_data.get("adjustment_applied_amount"),
            adjustment_exchange_rate=record_data.get("adjustment_exchange_rate"),
        )

        processed = ProcessedRecord(
            invoice_id=record_id,
            idempotency_key=idempotency_key,
        )

        db.add(ar_record)
        db.add(processed)
        db.commit()

        logger.info("record_ingested", record_id=record_id, workflow_id=workflow_id)
        return {"status": "INGESTED", "record_id": record_id}
    finally:
        db.close()


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

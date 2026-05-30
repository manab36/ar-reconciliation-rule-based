from sqlalchemy.orm import Session

from database_ops.model import ARRecord


class RecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_ar_record_by_customer_id(self, customer_id: str):
        return self.db.query(ARRecord).filter_by(customer_id=customer_id).first()

    # Add more methods as needed for other record queries
    def get_processed_record_by_idempotency_key(self, idempotency_key: str):
        from database_ops.model import ProcessedRecord
        return self.db.query(ProcessedRecord).filter_by(idempotency_key=idempotency_key).first()

    def insert_ar_record_and_processed(self, ar_record, processed_record):
        # List of columns to check for numeric type
        numeric_cols = [
            "customer_balance", "invoice_total", "invoice_applied_amount", "invoice_exchange_rate",
            "payment_total", "payment_applied_amount", "payment_exchange_rate",
            "credit_total", "credit_applied_amount", "credit_exchange_rate",
            "adjustment_total", "adjustment_applied_amount", "adjustment_exchange_rate"
        ]
        # List of exchange rate columns to check for positivity
        positive_cols = [
            "invoice_exchange_rate", "payment_exchange_rate", "credit_exchange_rate", "adjustment_exchange_rate"
        ]

        for col in numeric_cols:
            value = getattr(ar_record, col, None)
            if not isinstance(value, (int, float)):
                raise ValueError(f"{col} must be numeric, got {type(value).__name__}")

        for col in positive_cols:
            value = getattr(ar_record, col, None)
            if value is not None and value <= 0:
                raise ValueError(f"{col} must be positive, got {value}")

        self.db.add(ar_record)
        self.db.add(processed_record)
        try:
            self.db.flush()
        except Exception:
            self.db.rollback()
            raise

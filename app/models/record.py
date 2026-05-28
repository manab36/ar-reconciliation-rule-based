from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String

from app.core.database import Base


class ARRecord(Base):
    __tablename__ = "ar_records"

    id = Column(String, primary_key=True)
    customer_id = Column(String, nullable=False, index=True)
    customer_name = Column(String, nullable=True)
    customer_balance = Column(Float, nullable=True)
    invoice_total = Column(Float, nullable=True)
    invoice_applied_amount = Column(Float, nullable=True)
    invoice_exchange_rate = Column(Float, nullable=True)
    payment_total = Column(Float, nullable=True)
    payment_applied_amount = Column(Float, nullable=True)
    payment_exchange_rate = Column(Float, nullable=True)
    credit_total = Column(Float, nullable=True)
    credit_applied_amount = Column(Float, nullable=True)
    credit_exchange_rate = Column(Float, nullable=True)
    adjustment_total = Column(Float, nullable=True)
    adjustment_applied_amount = Column(Float, nullable=True)
    adjustment_exchange_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ProcessedRecord(Base):
    __tablename__ = "processed_records"

    invoice_id = Column(String, primary_key=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

from decimal import Decimal


class ARRecordValidator:
    NUMERIC_FIELDS = [
        "customer_balance",
        "invoice_total",
        "invoice_applied_amount",
        "invoice_exchange_rate",
        "payment_total",
        "payment_applied_amount",
        "payment_exchange_rate",
        "credit_total",
        "credit_applied_amount",
        "credit_exchange_rate",
        "adjustment_total",
        "adjustment_applied_amount",
        "adjustment_exchange_rate",
    ]

    POSITIVE_FIELDS = [
        "invoice_exchange_rate",
        "payment_exchange_rate",
        "credit_exchange_rate",
        "adjustment_exchange_rate",
    ]

    @classmethod
    def validate(cls, ar_record):

        for field in cls.NUMERIC_FIELDS:
            value = getattr(ar_record, field)

            if value is None:
                continue

            if not isinstance(value, (int, float, Decimal)):
                raise ValueError(f"{field} must be numeric")

        for field in cls.POSITIVE_FIELDS:
            value = getattr(ar_record, field)

            if value is not None and value <= 0:
                raise ValueError(f"{field} must be positive")

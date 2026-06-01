from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database_ops.models import ARRecord
from database_ops.repositories.ar_record_repository import RecordRepository
from database_ops.validations.ar_record_validator import ARRecordValidator


class ARRecordService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RecordRepository(db)

    def create_record(
        self,
        customer_id: str,
        customer_balance: float,
        invoice_total: float,
        invoice_applied_amount: float,
        invoice_exchange_rate: float,
        payment_total: float,
        payment_applied_amount: float,
        payment_exchange_rate: float,
        credit_total: float,
        credit_applied_amount: float,
        credit_exchange_rate: float,
        adjustment_total: float,
        adjustment_applied_amount: float,
        adjustment_exchange_rate: float,
    ) -> ARRecord:

        existing = self.repo.get_by_customer_id(customer_id)

        if existing:
            return existing

        ar_record = ARRecord(
            customer_id=customer_id,
            customer_balance=customer_balance,
            invoice_total=invoice_total,
            invoice_applied_amount=invoice_applied_amount,
            invoice_exchange_rate=invoice_exchange_rate,
            payment_total=payment_total,
            payment_applied_amount=payment_applied_amount,
            payment_exchange_rate=payment_exchange_rate,
            credit_total=credit_total,
            credit_applied_amount=credit_applied_amount,
            credit_exchange_rate=credit_exchange_rate,
            adjustment_total=adjustment_total,
            adjustment_applied_amount=adjustment_applied_amount,
            adjustment_exchange_rate=adjustment_exchange_rate,
        )

        ARRecordValidator.validate(ar_record)

        return self.repo.create(ar_record)

    def get_record(
        self,
        record_id: str,
    ):
        return self.repo.get_by_id(record_id)

    def update_record(
        self,
        record_id: str,
        **kwargs,
    ):

        try:
            record = self.repo.get_by_id(
                record_id,
                lock_for_update=True,
            )
            if not record:
                raise ValueError(f"Record {record_id} not found")
            updated_record = self.repo.update(
                record,
                **kwargs,
            )
            ARRecordValidator.validate(updated_record)
            self.db.commit()
            return updated_record
        except IntegrityError:
            self.db.rollback()
            raise

    def delete_record(
        self,
        record_id: str,
    ):

        record = self.repo.get_by_id(
            record_id,
            lock_for_update=True,
        )
        if not record:
            raise ValueError(f"Record {record_id} not found")
        self.repo.delete(record)
        self.db.commit()

    def is_record_exists_by_customer_id(self, customer_id: str) -> bool:
        """
        Check if an AR record exists for the given customer_id.
        Returns True if exists, False otherwise.
        """
        record = self.repo.get_by_customer_id(customer_id)
        return record is not None

    def get_record_by_customer_id(self, customer_id: str) -> ARRecord | None:
        """
        Retrieve an ARRecord instance based on the given customer_id.
        Returns the ARRecord if found, otherwise None.
        """
        return self.repo.get_by_customer_id(customer_id)

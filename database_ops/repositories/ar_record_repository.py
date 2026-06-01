from sqlalchemy import select
from sqlalchemy.orm import Session

from database_ops.models import (
    ARRecord,
    # ProcessedRecord,
)


class RecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        ar_record: ARRecord,
    ) -> ARRecord:

        self.db.add(ar_record)
        self.db.flush()

        return ar_record

    def get_by_id(
        self,
        record_id: str,
        lock_for_update: bool = False,
    ) -> ARRecord | None:

        stmt = select(ARRecord).where(ARRecord.id == record_id)

        if lock_for_update:
            stmt = stmt.with_for_update()

        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_customer_id(
        self,
        customer_id: str,
        lock_for_update: bool = False,
    ) -> ARRecord | None:

        stmt = select(ARRecord).where(ARRecord.customer_id == customer_id)

        if lock_for_update:
            stmt = stmt.with_for_update()

        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self) -> list[ARRecord]:

        stmt = select(ARRecord)

        return list(self.db.execute(stmt).scalars().all())

    def update(
        self,
        ar_record: ARRecord,
        **kwargs,
    ) -> ARRecord:

        for field, value in kwargs.items():
            if hasattr(ar_record, field):
                setattr(ar_record, field, value)

        self.db.flush()

        return ar_record

    def delete(
        self,
        ar_record: ARRecord,
    ) -> None:

        self.db.delete(ar_record)
        self.db.flush()

    # def get_processed_record_by_idempotency_key(
    #     self,
    #     idempotency_key: str,
    # ) -> ProcessedRecord | None:

    #     stmt = (
    #         select(ProcessedRecord)
    #         .where(
    #             ProcessedRecord.idempotency_key == idempotency_key
    #         )
    #     )

    #     return self.db.execute(stmt).scalar_one_or_none()

    # def create_ar_record(
    #     self,
    #     ar_record: ARRecord,
    # ) -> ARRecord:

    #     self.db.add(ar_record)
    #     self.db.flush()

    #     return ar_record

    # def create_processed_record(
    #     self,
    #     processed_record: ProcessedRecord,
    # ) -> ProcessedRecord:

    #     self.db.add(processed_record)
    #     self.db.flush()

    #     return processed_record

    # def create_ar_record_with_processed(
    #     self,
    #     ar_record: ARRecord,
    #     processed_record: ProcessedRecord,
    # ) -> tuple[ARRecord, ProcessedRecord]:

    #     self.db.add(ar_record)
    #     self.db.add(processed_record)

    #     self.db.flush()

    #     return ar_record, processed_record

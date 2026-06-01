from sqlalchemy import select
from sqlalchemy.orm import Session

from database_ops.models import ProcessedRecord


class ProcessedRecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, processed_record: ProcessedRecord) -> ProcessedRecord:
        """Create a new processed record."""
        self.db.add(processed_record)
        self.db.flush()
        return processed_record

    def get_by_id(
        self,
        record_id: str,
        lock_for_update: bool = False,
    ) -> ProcessedRecord | None:
        """Get processed record by ID."""
        stmt = select(ProcessedRecord).where(ProcessedRecord.id == record_id)
        if lock_for_update:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_workflow_id(
        self,
        workflow_id: str,
        lock_for_update: bool = False,
    ) -> ProcessedRecord | None:
        """Get processed record by workflow ID."""
        stmt = select(ProcessedRecord).where(ProcessedRecord.workflow_id == workflow_id)
        if lock_for_update:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_customer_id(
        self,
        customer_id: str,
        lock_for_update: bool = False,
    ) -> ProcessedRecord | None:
        """Get processed record by customer ID (returns most recent)."""
        stmt = (
            select(ProcessedRecord)
            .where(ProcessedRecord.customer_id == customer_id)
            .order_by(ProcessedRecord.created_at.desc())
        )
        if lock_for_update:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self) -> list[ProcessedRecord]:
        """Get all processed records."""
        stmt = select(ProcessedRecord).order_by(ProcessedRecord.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_by_verdict(self, verdict: str) -> list[ProcessedRecord]:
        """Get all processed records with a specific verdict."""
        stmt = (
            select(ProcessedRecord)
            .where(ProcessedRecord.verdict == verdict)
            .order_by(ProcessedRecord.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def update(self, processed_record: ProcessedRecord, **kwargs) -> ProcessedRecord:
        """Update a processed record."""
        for field, value in kwargs.items():
            if hasattr(processed_record, field):
                setattr(processed_record, field, value)
        self.db.flush()
        return processed_record

    def delete(self, processed_record: ProcessedRecord) -> None:
        """Delete a processed record."""
        self.db.delete(processed_record)
        self.db.flush()

    def exists_by_workflow_id(self, workflow_id: str) -> bool:
        """Check if a processed record exists for a workflow."""
        stmt = select(ProcessedRecord.id).where(
            ProcessedRecord.workflow_id == workflow_id
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None

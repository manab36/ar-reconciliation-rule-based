import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id = Column(String, unique=True, nullable=False, index=True)
    customer_id = Column(String, nullable=True)
    status = Column(
        String, nullable=False, default="PENDING"
    )  # PENDING, RUNNING, COMPLETED, FAILED
    current_stage = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    stages = relationship(
        "WorkflowStageState", back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowStageState(Base):
    __tablename__ = "workflow_stage_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String, nullable=False, index=True)
    stage_name = Column(String, nullable=False)
    status = Column(
        String, nullable=False, default="PENDING"
    )  # PENDING, RUNNING, SUCCESS, FAILED
    output_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workflow = relationship(
        "WorkflowRun",
        back_populates="stages",
        foreign_keys=[workflow_id],
        primaryjoin="WorkflowStageState.workflow_id == WorkflowRun.id",
    )

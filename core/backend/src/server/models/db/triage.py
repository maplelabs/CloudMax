"""
Database model for Alert Triage details.

This module defines the database table structure for storing alert triage
analysis information, including job tracking, analysis results, and metadata.
"""
from sqlalchemy import Column, ForeignKey, Integer, String, Text, Numeric, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin
from ..api.enums import Status


class Triage(TimestampMixin, Base):
    """
    Database model for storing alert triage analysis details.

    This table tracks the lifecycle of alert triage analysis,
    including job metadata, analysis results, and performance metrics.
    """
    __tablename__ = "triages"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key relationship to alerts table
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Triage status and lifecycle
    status = Column(SAEnum(Status, name="status_enum"), nullable=True, index=True)

    # LangGraph thread ID and RQ job ID
    thread_id = Column(String(255), nullable=True, index=True)
    job_id = Column(String(255), nullable=True, index=True)

    # Error message (if any)
    error_message = Column(Text, nullable=True)

    # Analysis results
    root_cause_summary = Column(Text, nullable=True)

    # Performance metrics
    tokens_used = Column(Integer, nullable=True)
    price_usd = Column(Numeric(10, 4), nullable=True)
    processing_time_sec = Column(Integer, nullable=True)
    llm_metrics = Column(JSONB, nullable=True, doc="LLM metrics tracker output including latency and call counts")

    # Relationships
    alert = relationship("Alert", back_populates="triage_sessions")

    def __repr__(self):
        return (
            f"<Triage(id={self.id}, alert_id={self.alert_id}, status='{self.status}', "
            f"thread_id='{self.thread_id}', job_id='{self.job_id}')>"
        )

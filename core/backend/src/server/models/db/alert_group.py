"""
Database model for Alert Groups.

This module defines the database table structure for storing alert groups,
which represent collections of related alerts that share a common root cause.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Numeric,
    CheckConstraint,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB

from .base import Base, TimestampMixin
from ..api.enums import Severity


class AlertGroup(TimestampMixin, Base):
    """
    Database model for storing alert groups.

    An alert group represents a collection of related alerts that likely
    share a common root cause. Groups are created by the grouping algorithm
    and can be triaged as a single unit.
    """

    __tablename__ = "alert_groups"

    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String(500), nullable=False)

    # Group status
    # active: Group is accepting new alerts
    # resolved: All alerts in group are resolved
    status = Column(String(50), default="active", nullable=False)

    # Group metadata
    # MAX(alert severities) in the group
    severity = Column(
        SAEnum(Severity, name="severity_enum"), nullable=False, default=Severity.P3
    )

    # Triage information (populated by triage worker)
    root_cause_summary = Column(Text, nullable=True)  # RCA from LLM
    triage_status = Column(
        String(50), default="pending", nullable=False
    )  # pending, in_progress, completed, failed
    triaged_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # LangGraph thread ID and RQ job ID (for journey tracking)
    thread_id = Column(
        String(255), nullable=True, index=True
    )  # Links to checkpoint DB for journey retrieval
    job_id = Column(String(255), nullable=True, index=True)  # RQ job ID for tracking

    # Error message (if triage fails)
    error_message = Column(Text, nullable=True)

    # CRITICAL FIX: Retry mechanism for failed groups
    retry_count = Column(Integer, default=0, nullable=False)  # Number of retry attempts

    # Performance metrics
    tokens_used = Column(Integer, nullable=True)
    price_usd = Column(Numeric(10, 4), nullable=True)
    processing_time_sec = Column(Integer, nullable=True)
    llm_metrics = Column(
        JSONB, nullable=True
    )  # LLM metrics tracker output including latency and call counts

    # Grouping decision metadata
    grouping_confidence = Column(
        Numeric(3, 2), nullable=True
    )  # LLM confidence score (0.00-1.00)
    grouping_reasoning = Column(
        Text, nullable=True
    )  # LLM explanation for grouping decision

    # Audit fields
    # created_at = first alert time (from TimestampMixin)
    # updated_at = last alert time (from TimestampMixin)

    # Relationship to alerts
    # Deleting a group should NOT delete alerts; alerts are ungrouped via ON DELETE SET NULL
    alerts = relationship("Alert", back_populates="group", lazy="select")

    # Relationship to evaluations
    # Deleting a group should delete its evaluations via ON DELETE CASCADE
    evaluations = relationship(
        "Evaluation",
        back_populates="group",
        lazy="select",
        foreign_keys="[Evaluation.group_id]",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'resolved')", name="chk_alert_group_status"
        ),
        CheckConstraint(
            "triage_status IN ('pending', 'in_progress', 'completed', 'failed')",
            name="chk_alert_group_triage_status",
        ),
        CheckConstraint(
            "grouping_confidence >= 0.00 AND grouping_confidence <= 1.00",
            name="chk_alert_group_confidence",
        ),
    )

    @property
    def alert_count(self) -> int:
        """
        Computed property for alert count.
        Returns the number of alerts in this group.

        Note: This uses len() on the loaded relationship. For better performance
        when you only need the count, use a query with COUNT(*) instead.
        """
        return len(self.alerts) if self.alerts else 0

    def __repr__(self):
        return f"<AlertGroup(id={self.id}, name='{self.group_name}', status='{self.status}', alerts={self.alert_count})>"

"""
Database model for Alert Evaluation details.

Defines the schema for storing evaluation metrics for an alert, including
scores, usage, and billing information.
"""
from sqlalchemy import Column, ForeignKey, Integer, String, Numeric, Enum as SAEnum, CheckConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin
from ..api.enums import Status


class Evaluation(TimestampMixin, Base):
    """SQLAlchemy model for evaluations table - supports both alerts and groups"""
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key relationships - exactly one must be set
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("alert_groups.id", ondelete="CASCADE"), nullable=True, index=True)

    # Evaluation status and job refs
    status = Column(SAEnum(Status, name="status_enum"), nullable=True, index=True)
    job_id = Column(String(255), nullable=True, index=True)

    # Evaluation scores - DeepEval metrics
    root_cause_similarity_percent = Column(
        Integer,
        CheckConstraint('root_cause_similarity_percent >= 0 AND root_cause_similarity_percent <= 100',
                        name='check_root_cause_similarity_percent_range'),
        nullable=True
    )

    # Determines how well the supervisor coordinates the conversation by using agents and KB tool given to it
    orch_agent_util_score_percent = Column(
        Integer,
        CheckConstraint('orch_agent_util_score_percent >= 0 AND orch_agent_util_score_percent <= 100',
                        name='orch_agent_util_score_percent_range'),
        nullable=True
    )

    # Determines how well the orchestrator completes the alert triaging task
    orch_task_completion_score_percent = Column(
        Integer,
        CheckConstraint('orch_task_completion_score_percent >= 0 AND orch_task_completion_score_percent <= 100',
                        name='orch_task_completion_score_percent_range'),
        nullable=True
    )

    # Determines how well the agents use the tools given to them
    sub_agent_tool_util_score_percent = Column(
        Integer,
        CheckConstraint('sub_agent_tool_util_score_percent >= 0 AND sub_agent_tool_util_score_percent <= 100',
                        name='sub_agent_tool_util_score_percent_range'),
        nullable=True
    )

    # Determines how well the agents complete the task given to them
    sub_agent_task_completion_score = Column(
        Integer,
        CheckConstraint('sub_agent_task_completion_score >= 0 AND sub_agent_task_completion_score <= 100',
                        name='sub_agent_task_completion_score_range'),
        nullable=True
    )

    # Evaluation details
    reason = Column(Text, nullable=True, doc="Detailed reasons for each evaluation metric")

    # error message
    error_message = Column(Text, nullable=True)

    # Performance metrics
    tokens_used = Column(Integer, nullable=True)
    price_usd = Column(Numeric(10, 4), nullable=True)
    processing_time_sec = Column(Integer, nullable=True)
    llm_metrics = Column(JSONB, nullable=True, doc="LLM metrics tracker output including latency and call counts")

    # Relationships
    alert = relationship("Alert", back_populates="evaluations", foreign_keys=[alert_id])
    group = relationship("AlertGroup", back_populates="evaluations", foreign_keys=[group_id])

    def __repr__(self):
        return f"<Evaluation(id={self.id}, alert_id={self.alert_id}, status='{self.status}'"

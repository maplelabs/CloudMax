from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin
from ..api.constants import DEFAULT_ALERT_SOURCE, DEFAULT_SEVERITY
from ..api.enums import Severity


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String, nullable=False, index=True)
    payload = Column(JSONB, nullable=False)
    alert_source = Column(String, default=DEFAULT_ALERT_SOURCE)
    alert_status = Column(String, default="firing")
    severity = Column(SAEnum(Severity, name="severity_enum"), nullable=True, default=DEFAULT_SEVERITY)
    alert_name = Column(String, nullable=True)

    # TODO: Store the alert's start time as received from the alert source.
    #  This is needed for workflow mapping and to handle delays in notification

    # Alert grouping relationship
    # When a group is deleted, alerts are ungrouped (group_id set to NULL)
    group_id = Column(Integer, ForeignKey("alert_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    group = relationship("AlertGroup", back_populates="alerts")

    # Relationship to triage sessions and evaluations
    triage_sessions = relationship("Triage", back_populates="alert")
    evaluations = relationship("Evaluation", back_populates="alert")

    # Relationship to fault ledger through mapping table
    fault_ledger = relationship(
        "FaultLedger",
        secondary="fault_ledger_to_alerts",
        back_populates="alerts",
        uselist=False
    )

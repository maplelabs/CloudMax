from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, UniqueConstraint, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin
from ..api.enums import FaultLedgerStatus


class FaultLedger(TimestampMixin, Base):
    """Database model for Fault Ledger entries."""
    __tablename__ = "fault_ledger"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fault_name = Column(String, nullable=False)
    fault_description = Column(String, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(SAEnum(FaultLedgerStatus, name="fault_ledger_status", native_enum=False), nullable=False)
    configured_duration = Column(Float, nullable=False)
    target_system = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    trigger_mechanism = Column(String, nullable=False)
    session_id = Column(String, unique=True, nullable=False)
    alert_names = Column(JSON, nullable=True)  # List of alert names to filter by

    # Relationship to alerts through mapping table
    alerts = relationship(
        "Alert",
        secondary="fault_ledger_to_alerts",
        back_populates="fault_ledger"
    )


class FaultLedgerToAlertMapping(TimestampMixin, Base):
    """Mapping table between FaultLedger and Alert."""
    __tablename__ = "fault_ledger_to_alerts"

    __table_args__ = (
        UniqueConstraint('alert_id', name='uq_alert_single_fault_ledger'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    fault_ledger_id = Column(Integer, ForeignKey("fault_ledger.id", ondelete="CASCADE"), nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)

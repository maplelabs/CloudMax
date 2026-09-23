from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from src.server.models.api.enums import FaultLedgerStatus


class FaultLedgerCreateRequest(BaseModel):
    """Request model for creating a new FaultLedger entry (POST)"""
    fault_name: str = Field(..., description="Name of the fault")
    fault_description: str = Field(..., description="Description of the fault")
    start_time: datetime = Field(..., description="Start time of the fault")
    configured_duration: float = Field(..., description="Duration of the fault in seconds")
    target_system: str = Field(..., description="Target system affected by the fault")
    severity: str = Field(..., description="Severity level (low, medium, high, critical)")
    trigger_mechanism: str = Field(..., description="How the fault was triggered (manual, automated, etc.)")
    session_id: str = Field(..., description="Unique identifier for each fault session")
    alert_names: Optional[List[str]] = Field(None, description="List of alert names to filter by")


class FaultLedgerUpdateRequest(BaseModel):
    """Request model for updating a FaultLedger entry (PUT)"""
    end_time: Optional[datetime] = Field(None, description="End time of the fault")
    status: Optional[FaultLedgerStatus] = Field(None, description="Status of the fault (started, failed, completed)")


class FaultLedgerResponse(BaseModel):
    """Response model for FaultLedger"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    fault_name: str
    fault_description: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: FaultLedgerStatus
    configured_duration: float
    target_system: str
    severity: str
    trigger_mechanism: str
    session_id: str
    alert_names: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime


# Keep old models for backward compatibility
class FaultLedgerCreate(FaultLedgerCreateRequest):
    """Deprecated: Use FaultLedgerCreateRequest instead"""
    end_time: datetime = Field(..., description="End time of the fault")
    status: str = Field(..., description="Status of the fault")
    configured_duration: float = Field(..., description="Configured duration in seconds")

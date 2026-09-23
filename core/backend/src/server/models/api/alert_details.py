"""
Pydantic models for Alert Detail API endpoints.
"""
from datetime import datetime
from typing import Dict, Any

from pydantic import BaseModel, Field

from .constants import DEFAULT_SEVERITY, DEFAULT_ALERT_SOURCE
from .enums import Status, Severity


class AlertDetailResponse(BaseModel):
    """Response model for single alert detail endpoint"""
    id: str = Field(description="Unique alert identifier")
    external_id: str = Field(description="External alert identifier")
    name: str = Field(description="Alert name/title")
    severity: Severity = Field(default=DEFAULT_SEVERITY, description="Alert severity level")
    triage_status: Status = Field(description="Current triage status")
    evaluation_status: Status = Field(description="Current evaluation status")
    started_at: datetime = Field(description="When the alert was first triggered")
    created_at: datetime = Field(description="When the alert was created in the system")
    last_updated_at: datetime = Field(description="When the alert was last updated")
    alert_source: str = Field(default=DEFAULT_ALERT_SOURCE, description="Source system that generated the alert")
    alert_status: str = Field(description="Current alert status (e.g., firing, resolved)")
    payload: Dict[str, Any] = Field(description="Full alert payload from the source system")

"""
Pydantic models for Alert Group Detail API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from .enums import Severity


class AlertInGroup(BaseModel):
    """Individual alert within a group"""

    id: str = Field(description="Alert identifier")
    alert_name: str = Field(description="Alert name")
    severity: Severity = Field(description="Alert severity")
    alert_status: str = Field(description="Alert status (firing/resolved)")
    created_at: datetime = Field(description="When the alert was created")
    alert_source: str = Field(description="Source system")
    labels: Dict[str, Any] = Field(default_factory=dict, description="Alert labels")
    annotations: Dict[str, Any] = Field(default_factory=dict, description="Alert annotations")


class AlertGroupDetailResponse(BaseModel):
    """Response model for single alert group detail endpoint"""

    id: str = Field(description="Unique alert group identifier")
    group_name: str = Field(description="Alert group name")
    alert_count: int = Field(description="Number of alerts in this group")
    severity: Severity = Field(description="Alert group severity level")
    triage_status: str = Field(description="Current triage status")
    status: str = Field(description="Group status (active/resolved)")
    root_cause_summary: Optional[str] = Field(
        default=None, description="Root cause analysis summary"
    )
    created_at: datetime = Field(description="When the group was created")
    updated_at: datetime = Field(description="When the group was last updated")
    triaged_at: Optional[datetime] = Field(
        default=None, description="When triage was completed"
    )

    # Performance metrics
    tokens_used: Optional[int] = Field(
        default=None, description="Total tokens used in triage"
    )
    price_usd: Optional[float] = Field(
        default=None, description="Cost of triage in USD"
    )
    processing_time_sec: Optional[int] = Field(
        default=None, description="Processing time in seconds"
    )

    # Grouping metadata
    grouping_confidence: Optional[float] = Field(
        default=None, description="Grouping confidence score (0.00-1.00)"
    )
    grouping_reasoning: Optional[str] = Field(
        default=None, description="Reasoning for grouping decision"
    )

    # Alerts in this group
    alerts: List[AlertInGroup] = Field(description="List of alerts in this group")

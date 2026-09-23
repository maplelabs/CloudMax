"""
Pydantic models for Alert Group API endpoints.
"""

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field

from .enums import Status, Severity, Timeline
from .pagination_meta import PaginationMeta


class AlertGroupListRequest(BaseModel):
    """Request model for GET /v1/alert-groups (Query Parameters)"""

    # Pagination
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=10, ge=1, le=100, description="Items per page")
    # Filtering
    severity: Optional[Severity] = Field(
        default=None, description="Filter by severity level"
    )
    triage_status: Optional[Status] = Field(
        default=None, description="Filter by triage status"
    )
    name_contains: Optional[str] = Field(
        default=None, description="Filter by group name containing text"
    )
    status: Optional[str] = Field(
        default=None, description="Filter by group status (active/resolved)"
    )
    # Time range filtering
    time_range: Optional[Timeline] = Field(
        default=None, description="Filter by time range"
    )
    start_time: Optional[datetime] = Field(
        default=None, description="Custom range start time (ISO 8601 with timezone)"
    )
    end_time: Optional[datetime] = Field(
        default=None, description="Custom range end time (ISO 8601 with timezone)"
    )
    # Evaluation filtering
    evaluation_status: Optional[Status] = Field(
        default=None, description="Filter by evaluation status"
    )
    evaluation_score_operator: Optional[Literal[">", "<", ">=", "<="]] = Field(
        default=None, description="Score comparison operator"
    )
    evaluation_score_value: Optional[float] = Field(
        default=None, ge=0, le=100, description="Score value for comparison (percentage)"
    )


class AlertGroupListItem(BaseModel):
    """Individual alert group item in the list response"""

    id: str = Field(description="Unique alert group identifier")
    group_name: str = Field(description="Alert group name")
    alert_count: int = Field(description="Number of alerts in this group")
    severity: Severity = Field(description="Alert group severity level")
    triage_status: str = Field(
        description="Current triage status (pending/in_progress/completed/failed)"
    )
    status: str = Field(description="Group status (active/resolved)")
    evaluation_score: Optional[float] = Field(
        default=None, ge=0, le=100, description="Evaluation score as percentage"
    )
    created_at: datetime = Field(description="When the group was created")
    updated_at: datetime = Field(description="When the group was last updated")
    triaged_at: Optional[datetime] = Field(
        default=None, description="When triage was completed"
    )


class AlertGroupListResponse(BaseModel):
    """Response for alert group list endpoint"""

    groups: list[AlertGroupListItem] = Field(
        description="List of alert groups for current page"
    )
    pagination: PaginationMeta = Field(description="Pagination information")

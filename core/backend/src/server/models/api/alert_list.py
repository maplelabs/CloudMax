"""
Pydantic models for Alert API endpoints.
"""
from datetime import datetime, timedelta
from typing import Optional, Literal, Tuple

from pydantic import BaseModel, Field

from .constants import DEFAULT_TIMELINE, DEFAULT_SEVERITY, DEFAULT_ALERT_SOURCE, MAX_CUSTOM_RANGE_DAYS
from .enums import Status, Severity, Timeline
from .pagination_meta import PaginationMeta


def validate_custom_time_range(
    time_range: Optional[Timeline],
    start_time: Optional[datetime],
    end_time: Optional[datetime]
) -> Tuple[bool, Optional[str]]:
    """
    Validate custom time range parameters.

    Returns:
        Tuple of (is_valid, error_message). If is_valid is True, error_message is None.
    """
    if time_range != Timeline.CUSTOM:
        return True, None

    if not start_time or not end_time:
        return False, "start_time and end_time are required when time_range is 'custom'"

    if start_time >= end_time:
        return False, "start_time must be before end_time"

    if (end_time - start_time) > timedelta(days=MAX_CUSTOM_RANGE_DAYS):
        return False, f"Custom time range cannot exceed {MAX_CUSTOM_RANGE_DAYS} days"

    return True, None


class AlertListRequest(BaseModel):
    """Request model for GET /v1/alerts (Query Parameters)"""
    # Pagination
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=10, ge=1, le=100, description="Items per page")
    # Filtering
    severity: Optional[Severity] = Field(default=None, description="Filter by severity level")
    triage_status: Optional[Status] = Field(default=None, description="Filter by triage status")
    evaluation_status: Optional[Status] = Field(default=None, description="Filter by evaluation status")
    name_contains: Optional[str] = Field(default=None, description="Filter by alert name containing text")
    time_range: Optional[Timeline] = Field(default=DEFAULT_TIMELINE, description="Filter by time range")
    evaluation_score_operator: Optional[Literal[">", "<", ">=", "<="]] = Field(default=None,
                                                                               description="Score comparison operator")
    evaluation_score_value: Optional[float] = Field(default=None, ge=0, le=100,
                                                    description="Score value for comparison (percentage)")
    ungrouped_only: Optional[bool] = Field(default=None, description="Filter to show only ungrouped alerts (alerts not in any group)")
    # Custom time range fields
    start_time: Optional[datetime] = Field(default=None, description="Custom range start time (ISO 8601 with timezone)")
    end_time: Optional[datetime] = Field(default=None, description="Custom range end time (ISO 8601 with timezone)")


class AlertListItem(BaseModel):
    """Individual alert item in the list response"""
    id: str = Field(description="Unique alert identifier")
    name: str = Field(description="Alert name/title")
    severity: Severity = Field(default=DEFAULT_SEVERITY, description="Alert severity level")
    triage_status: Status = Field(description="Current triage status")
    evaluation_status: Status = Field(description="Current evaluation status")
    evaluation_score: Optional[float] = Field(default=None, ge=0, le=100,
                                              description="Evaluation confidence score as percentage")
    started_at: datetime = Field(description="When the alert was first triggered")
    last_updated_at: datetime = Field(description="When the alert was last updated")
    alert_source: str = Field(default=DEFAULT_ALERT_SOURCE, description="Source system that generated the alert")


class AlertListResponse(BaseModel):
    """Response for alert list endpoint"""
    alerts: list[AlertListItem] = Field(description="List of alerts for current page")
    pagination: PaginationMeta = Field(description="Pagination information")

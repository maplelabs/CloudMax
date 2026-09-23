"""
Pydantic models for removing alerts from existing groups.
"""

from pydantic import BaseModel, Field
from typing import List


class RemoveAlertsFromGroupRequest(BaseModel):
    """Request model for removing alerts from an existing group"""
    alert_ids: List[str] = Field(description="List of alert IDs to remove from the group", min_length=1)


class RemoveAlertsFromGroupResponse(BaseModel):
    """Response model for removing alerts from group"""
    group_id: int = Field(description="ID of the group")
    group_name: str = Field(description="Name of the group")
    alerts_removed: int = Field(description="Number of alerts removed")
    remaining_alerts: int = Field(description="Number of alerts remaining in the group")
    message: str = Field(description="Success message")

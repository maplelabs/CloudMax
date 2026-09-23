"""
Pydantic models for adding alerts to existing groups.
"""

from pydantic import BaseModel, Field
from typing import List


class AddAlertsToGroupRequest(BaseModel):
    """Request model for adding alerts to an existing group"""
    alert_ids: List[str] = Field(description="List of alert IDs to add to the group", min_length=1)


class AddAlertsToGroupResponse(BaseModel):
    """Response model for adding alerts to group"""
    group_id: int = Field(description="ID of the group")
    group_name: str = Field(description="Name of the group")
    alerts_added: int = Field(description="Number of alerts added")
    total_alerts: int = Field(description="Total number of alerts in the group after adding")
    message: str = Field(description="Success message")

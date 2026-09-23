"""
Pydantic models for the FastAPI SRE Alert Dashboard.
"""
from datetime import datetime
from typing import List, Union

from pydantic import BaseModel, Field

from .enums import ToolResponseType


class BaseTriageMessage(BaseModel):
    """Base class for all triage messages."""
    timestamp: datetime = Field(default_factory=datetime.now)


class TriageAIMessage(BaseTriageMessage):
    """AI agent response messages."""
    agent_name: str
    content: str


class TriageToolMessage(BaseTriageMessage):
    """Tool call and response messages."""
    agent_name: str
    tool_name: str
    tool_args: str
    tool_response: str
    response_type: ToolResponseType


class TriageJourneyResponse(BaseModel):
    """Response for alert triage journey endpoint"""
    alert_id: str = Field(description="Alert identifier")
    messages: List[Union[TriageAIMessage, TriageToolMessage]] = Field(description="List of triage messages")

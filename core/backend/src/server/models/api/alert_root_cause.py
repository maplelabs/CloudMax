"""
Pydantic models for Alert Root Cause Analysis API endpoints.
"""
from pydantic import BaseModel, Field


class TriageRCAResponse(BaseModel):
    """Response model for root cause analysis endpoint that returns markdown content."""
    content: str = Field(description="Root cause analysis in markdown format")

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response for the application"""
    message: str = Field(description="Error message to display to user")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),
                                description="When the error occurred")

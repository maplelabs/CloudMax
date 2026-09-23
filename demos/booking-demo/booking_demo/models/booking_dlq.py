"""Pydantic models for DLQ booking check results."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class BookingDLQStatus(str, Enum):
    """Status of booking DLQ check."""
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"


class BookingDLQResult(BaseModel):
    """Simple result: Is the booking in the DLQ or not?"""
    booking_id: int
    status: BookingDLQStatus
    topic: str
    message: str
    error: Optional[str] = None


"""Pydantic models for get bookings by time range results."""
from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class BookingsByTimeRangeResult(BaseModel):
    """Result of querying bookings by time range."""
    booking_ids: list[int]
    count: int
    table_name: str
    start_time: datetime
    end_time: datetime
    error: Optional[str] = None


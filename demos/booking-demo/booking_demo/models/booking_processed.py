"""Pydantic models for check_booking_processed tool responses."""
from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class BookingProcessedStatus(str, Enum):
    """Status of booking processing check."""
    PROCESSED = "PROCESSED"  # Consumer consumed + stored in booking_details
    PENDING = "PENDING"  # Message in Kafka but consumer hasn't reached it (lag)
    CONSUMED_BUT_NOT_PROCESSED = "CONSUMED_BUT_NOT_PROCESSED"  # Consumed but not in DB
    PRODUCER_EXCEPTION = "PRODUCER_EXCEPTION"  # Booking created but never published to Kafka
    BOOKING_NOT_FOUND = "BOOKING_NOT_FOUND"  # Booking ID doesn't exist in booking_info


class BookingProcessedResult(BaseModel):
    """Result of check_booking_processed tool."""
    booking_id: int = Field(description="The booking ID that was checked")
    status: BookingProcessedStatus = Field(description="Processing status")
    created_at: Optional[datetime] = Field(
        default=None, 
        description="Booking creation timestamp from booking_info table"
    )
    message_offset: Optional[int] = Field(
        default=None, 
        description="Kafka offset where the booking message was found"
    )
    consumer_offset: Optional[int] = Field(
        default=None, 
        description="Current committed offset of the consumer group"
    )
    lag: Optional[int] = Field(
        default=None, 
        description="Number of messages behind (if status is PENDING)"
    )
    in_booking_details: Optional[bool] = Field(
        default=None, 
        description="Whether booking exists in booking_details table"
    )
    message: Optional[str] = Field(
        default=None, 
        description="Human-readable explanation of the status"
    )
    error: Optional[str] = Field(
        default=None, 
        description="Error message if operation failed"
    )
    
    # Additional diagnostic info
    topic: Optional[str] = Field(
        default=None,
        description="Kafka topic that was searched"
    )
    consumer_group: Optional[str] = Field(
        default=None,
        description="Consumer group whose offset was checked"
    )
    search_range_start: Optional[datetime] = Field(
        default=None,
        description="Start of time range searched in Kafka"
    )
    search_range_end: Optional[datetime] = Field(
        default=None,
        description="End of time range searched in Kafka"
    )
    messages_scanned: Optional[int] = Field(
        default=None,
        description="Number of Kafka messages scanned in the time range"
    )


"""Pydantic models for consumer lag responses."""
from typing import Optional
from pydantic import BaseModel, Field


class PartitionLag(BaseModel):
    """Lag information for a single partition."""
    topic: str = Field(description="Topic name")
    partition: int = Field(description="Partition number")
    current_offset: int = Field(description="Current committed offset")
    log_end_offset: int = Field(description="Log end offset (high watermark)")
    lag: int = Field(description="Number of messages behind")


class ConsumerLagResult(BaseModel):
    """Consumer lag result with per-partition details."""
    consumer_group: str = Field(description="Consumer group ID")
    topic: Optional[str] = Field(default=None, description="Topic filter (if specified)")
    total_lag: Optional[int] = Field(default=None, description="Total lag across all partitions")
    partition_count: Optional[int] = Field(default=None, description="Number of partitions")
    partitions: Optional[list[PartitionLag]] = Field(default=None, description="Per-partition lag details")
    error: Optional[str] = Field(default=None, description="Error message if operation failed")


"""Pydantic models for PostgreSQL diagnostic tool responses."""
from typing import Optional, List
from pydantic import BaseModel, Field


# =============================================================================
# Tool 1: db.checkAccess - Response Model
# =============================================================================
class CheckAccessResult(BaseModel):
    """Response model for database accessibility check."""
    db_accessible: bool = Field(description="Whether the database is reachable")
    error: Optional[str] = Field(default=None, description="Error message if connection failed")


# =============================================================================
# Tool 2: db.checkWriteLocks - Response Model
# =============================================================================
class WriteLockInfo(BaseModel):
    """Information about a single pending write lock."""
    pid: int = Field(description="Process ID holding/waiting for the lock")
    table_name: Optional[str] = Field(default=None, description="Table being locked")
    lock_mode: str = Field(description="Type of lock (e.g., RowExclusiveLock)")
    granted: bool = Field(description="Whether the lock has been granted")
    query: Optional[str] = Field(default=None, description="Query being executed")
    state: Optional[str] = Field(default=None, description="State of the process")


class CheckWriteLocksResult(BaseModel):
    """Response model for write locks check."""
    has_pending_locks: bool = Field(description="Whether there are pending write locks")
    pending_lock_count: int = Field(description="Number of pending write locks")
    locks: Optional[List[WriteLockInfo]] = Field(default=None, description="Details of pending locks")
    error: Optional[str] = Field(default=None, description="Error message if query failed")


# =============================================================================
# Tool 3: db.checkMaxConnections - Response Model
# =============================================================================
class CheckMaxConnectionsResult(BaseModel):
    """Response model for max connections check."""
    connection_count: int = Field(description="Current number of active connections")
    max_connection_limit: int = Field(description="Maximum allowed connections (from pg_settings)")
    max_connections_reached: bool = Field(description="Whether max connections limit is reached or near saturation")
    usage_percentage: float = Field(description="Percentage of connections used")
    error: Optional[str] = Field(default=None, description="Error message if query failed")


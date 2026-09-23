"""
API models for job-related responses.
"""

from typing import Optional, Dict, Any

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    """Response model for job status."""
    job_id: str
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

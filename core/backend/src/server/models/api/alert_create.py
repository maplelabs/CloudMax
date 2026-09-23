"""
API models for manual alert creation.
"""
from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field, field_validator

from .enums import Severity


class ManualAlertCreateRequest(BaseModel):
    """Request model for creating a manual alert."""
    
    # Required fields
    alert_name: str = Field(
        ...,
        description="Alert name/title",
        min_length=1,
        examples=["High CPU Usage on Production Server"]
    )
    
    severity: Severity = Field(
        ...,
        description="Alert severity level (P1/P2/P3)"
    )
    
    description: str = Field(
        ...,
        description="Alert description",
        min_length=1,
        examples=["CPU usage exceeded 90% threshold on prod-server-01"]
    )
    
    alert_status: Literal["firing", "resolved"] = Field(
        default="firing",
        description="Alert status"
    )
    
    # Optional fields
    labels: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Additional labels for the alert",
        examples=[{"environment": "production", "server": "prod-server-01"}]
    )
    
    annotations: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Additional annotations for the alert",
        examples=[{"runbook": "https://wiki.company.com/runbooks/high-cpu"}]
    )
    
    # Triage control
    trigger_triage: bool = Field(
        default=True,
        description="Whether to trigger triage immediately upon creation"
    )

    @field_validator('alert_name', 'description')
    @classmethod
    def validate_string_length(cls, v: str) -> str:
        """Validate that string fields don't exceed reasonable limits."""
        if len(v) > 500:
            raise ValueError(f"Field exceeds maximum length of 500 characters (got {len(v)})")
        return v

    @field_validator('labels', 'annotations')
    @classmethod
    def validate_dict_size(cls, v: Optional[Dict[str, str]]) -> Dict[str, str]:
        """
        Validate labels/annotations to prevent DoS attacks.

        Limits:
        - Maximum 50 keys per dictionary
        - Maximum 100 characters per key
        - Maximum 500 characters per value
        """
        if v is None:
            return {}

        # Check number of keys
        if len(v) > 50:
            raise ValueError(f"Dictionary exceeds maximum of 50 keys (got {len(v)})")

        # Check key and value lengths
        for key, value in v.items():
            if len(key) > 100:
                raise ValueError(f"Key '{key[:20]}...' exceeds maximum length of 100 characters (got {len(key)})")
            if len(value) > 500:
                raise ValueError(f"Value for key '{key}' exceeds maximum length of 500 characters (got {len(value)})")

        return v


class ManualAlertCreateResponse(BaseModel):
    """Response model for manual alert creation."""

    success: bool = Field(description="Whether the alert was created successfully")
    message: str = Field(description="Success or error message")
    alert_id: str = Field(description="External ID of the created alert (for navigation)")
    triage_triggered: bool = Field(description="Whether triage was triggered")

    @field_validator('alert_id')
    @classmethod
    def validate_alert_id(cls, v: str, values) -> str:
        """Validate that alert_id is non-empty when success is True."""
        if not v or not v.strip():
            raise ValueError("alert_id must be non-empty")
        return v

    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate that message is non-empty."""
        if not v or not v.strip():
            raise ValueError("message must be non-empty")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Alert created successfully",
                "alert_id": "manual__1719034441__a7b3c9d1",
                "triage_triggered": True
            }
        }

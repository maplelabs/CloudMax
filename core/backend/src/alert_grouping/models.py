"""Data models for alert grouping."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from dateutil import parser as dateutil_parser


logger = logging.getLogger(__name__)


class GroupingAction(str, Enum):
    """Possible grouping actions."""

    JOIN_GROUP = "join_group"
    CREATE_NEW_GROUP = "create_new_group"
    SKIP = "skip"


class Severity(str, Enum):
    """Alert severity levels."""

    P1 = "P1"  # Critical
    P2 = "P2"  # High
    P3 = "P3"  # Medium
    P4 = "P4"  # Low


def parse_timestamp(
    timestamp_str: str, field_name: str, alert_id: Optional[str] = None
) -> datetime:
    """Parse ISO-8601 timestamps and normalize to UTC."""
    if not timestamp_str:
        raise ValueError(f"{field_name} cannot be empty")

    try:
        dt = dateutil_parser.isoparse(timestamp_str)

        if dt.tzinfo is None:
            logger.warning(
                "Alert %s has %s without timezone, assuming UTC",
                alert_id or "UNKNOWN",
                field_name,
            )
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Invalid {field_name} format: '{timestamp_str}'. Expected ISO 8601 format. Error: {e}"
        )


def validate_dict_field(
    data: Any,
    field_name: str,
    max_keys: int = 50,
    max_value_length: int = 1000,
) -> Dict[str, str]:
    """Validate and sanitize dictionary-like fields (labels/annotations)."""
    if not data:
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be a dictionary")

    if len(data) > max_keys:
        raise ValueError(f"{field_name} cannot have more than {max_keys} keys")

    validated: Dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")

        if len(key) > 100:
            raise ValueError(f"{field_name} key too long: {key[:50]}...")

        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"{field_name}[{key}] must be a simple type")

        value_str = str(value)
        if len(value_str) > max_value_length:
            logger.warning(
                "%s[%s] truncated from %d to %d chars",
                field_name,
                key,
                len(value_str),
                max_value_length,
            )
            value_str = value_str[:max_value_length]

        validated[key] = value_str

    return validated


@dataclass
class Alert:
    """Represents a single alert."""

    id: str
    alert_name: str
    severity: Severity
    alert_source: str
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    starts_at: datetime
    ends_at: Optional[datetime] = None
    fingerprint: Optional[str] = None
    group_id: Optional[int] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alert":
        """
        Create Alert from dictionary with comprehensive validation.

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # HIGH PRIORITY: Validate required fields
        # Extract ID (required)
        alert_id = data.get("id") or data.get("fingerprint")
        if not alert_id:
            raise ValueError("Alert must have either 'id' or 'fingerprint' field")

        # Extract alert name (required)
        alert_name = data.get("alert_name") or data.get("labels", {}).get("alertname")
        if not alert_name:
            raise ValueError(
                "Alert must have either 'alert_name' or 'labels.alertname' field"
            )

        # HIGH PRIORITY: Validate severity enum
        severity_str = data.get("severity", "P3")
        try:
            severity = Severity(severity_str)
        except ValueError:
            # Invalid severity - use P3 as fallback and log warning
            logger.warning(
                "Invalid severity value '%s' for alert %s. Using P3 as fallback. Valid values: %s",
                severity_str,
                alert_id,
                [s.value for s in Severity],
            )
            severity = Severity.P3

        # HIGH PRIORITY: Validate timestamp parsing
        # Parse starts_at (required)
        starts_at_str = data.get("starts_at")
        if not starts_at_str:
            raise ValueError(f"Alert {alert_id} missing required field 'starts_at'")

        starts_at = parse_timestamp(starts_at_str, "starts_at", alert_id=alert_id)

        # Parse ends_at (optional)
        ends_at = None
        ends_at_str = data.get("ends_at")
        if ends_at_str:
            try:
                ends_at = parse_timestamp(ends_at_str, "ends_at", alert_id=alert_id)
            except ValueError as e:
                # Log warning but don't fail - ends_at is optional
                logger.warning(
                    "Alert %s has invalid 'ends_at' timestamp '%s': %s. Ignoring ends_at.",
                    alert_id,
                    ends_at_str,
                    e,
                )

        return cls(
            id=alert_id,
            alert_name=alert_name,
            severity=severity,
            alert_source=data.get("alert_source", "prometheus"),
            status=data.get("status", "firing"),
            labels=validate_dict_field(data.get("labels", {}), "labels"),
            annotations=validate_dict_field(data.get("annotations", {}), "annotations"),
            starts_at=starts_at,
            ends_at=ends_at,
            fingerprint=data.get("fingerprint"),
            group_id=data.get("group_id"),
            raw_payload=data,
        )


@dataclass
class AlertGroup:
    """Represents a group of related alerts."""

    id: int
    group_name: str
    severity: Severity
    status: str
    alerts: List[Alert] = field(default_factory=list)
    root_cause_summary: Optional[str] = None
    triage_status: str = "pending"
    grouping_confidence: Optional[float] = None
    grouping_reasoning: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_alert(self, alert: Alert):
        """Add an alert to this group and update severity to highest priority."""
        self.alerts.append(alert)
        alert.group_id = self.id

        # Update group severity to highest (P1 > P2 > P3 > P4)
        # Lower number = higher severity/priority
        severity_priority = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
        current_priority = severity_priority.get(self.severity.value, 4)
        alert_priority = severity_priority.get(alert.severity.value, 4)

        if alert_priority < current_priority:  # Lower number = higher severity
            self.severity = alert.severity

        self.updated_at = datetime.now(timezone.utc)

    def get_alert_count(self) -> int:
        """Get number of alerts in this group."""
        return len(self.alerts)


@dataclass
class GroupingDecision:
    """Represents an LLM grouping decision."""

    action: GroupingAction
    confidence: float
    reasoning: str
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    related_alert_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "related_alert_ids": self.related_alert_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupingDecision":
        """Create GroupingDecision from dictionary."""
        return cls(
            action=GroupingAction(data["action"]),
            confidence=data["confidence"],
            reasoning=data["reasoning"],
            group_id=data.get("group_id"),
            group_name=data.get("group_name"),
            related_alert_ids=data.get("related_alert_ids", []),
        )

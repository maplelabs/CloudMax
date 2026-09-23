"""Unit tests for alert grouping models."""

import pytest
from datetime import datetime, timezone
from src.alert_grouping.models import (
    Alert,
    AlertGroup,
    GroupingAction,
    GroupingDecision,
    Severity,
    parse_timestamp,
    validate_dict_field,
)


class TestParseTimestamp:
    """Tests for timestamp parsing functionality."""

    def test_parse_valid_iso8601_with_timezone(self):
        """Test parsing valid ISO 8601 timestamp with timezone."""
        timestamp_str = "2026-04-01T10:30:00+00:00"
        result = parse_timestamp(timestamp_str, "starts_at", "test-alert-1")
        
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 1

    def test_parse_valid_iso8601_without_timezone_assumes_utc(self):
        """Test parsing ISO 8601 without timezone assumes UTC."""
        timestamp_str = "2026-04-01T10:30:00"
        result = parse_timestamp(timestamp_str, "starts_at", "test-alert-1")
        
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_parse_empty_timestamp_raises_error(self):
        """Test that empty timestamp raises ValueError."""
        with pytest.raises(ValueError, match="starts_at cannot be empty"):
            parse_timestamp("", "starts_at", "test-alert-1")

    def test_parse_invalid_timestamp_raises_error(self):
        """Test that invalid timestamp format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid starts_at format"):
            parse_timestamp("not-a-timestamp", "starts_at", "test-alert-1")

    def test_parse_none_timestamp_raises_error(self):
        """Test that None timestamp raises ValueError."""
        with pytest.raises(ValueError):
            parse_timestamp(None, "starts_at", "test-alert-1")


class TestValidateDictField:
    """Tests for dictionary field validation."""

    def test_validate_empty_dict(self):
        """Test validating empty dictionary."""
        result = validate_dict_field({}, "labels")
        assert result == {}

    def test_validate_none_returns_empty_dict(self):
        """Test that None input returns empty dict."""
        result = validate_dict_field(None, "labels")
        assert result == {}

    def test_validate_dict_with_string_values(self):
        """Test validating dict with string values."""
        data = {"env": "production", "region": "us-east-1"}
        result = validate_dict_field(data, "labels")
        assert result == {"env": "production", "region": "us-east-1"}

    def test_validate_dict_with_mixed_types(self):
        """Test validating dict with mixed value types."""
        data = {"count": 42, "enabled": True, "ratio": 3.14}
        result = validate_dict_field(data, "labels")
        assert result == {"count": "42", "enabled": "True", "ratio": "3.14"}

    def test_validate_dict_truncates_long_values(self):
        """Test that long values are truncated."""
        long_value = "x" * 2000
        data = {"description": long_value}
        result = validate_dict_field(data, "annotations", max_value_length=1000)
        assert len(result["description"]) == 1000

    def test_validate_dict_rejects_too_many_keys(self):
        """Test that dict with too many keys raises error."""
        data = {f"key{i}": f"value{i}" for i in range(100)}
        with pytest.raises(ValueError, match="cannot have more than 50 keys"):
            validate_dict_field(data, "labels", max_keys=50)

    def test_validate_dict_rejects_non_string_keys(self):
        """Test that non-string keys raise error."""
        data = {123: "value"}
        with pytest.raises(ValueError, match="keys must be strings"):
            validate_dict_field(data, "labels")

    def test_validate_dict_rejects_long_keys(self):
        """Test that keys longer than 100 chars raise error."""
        long_key = "x" * 150
        data = {long_key: "value"}
        with pytest.raises(ValueError, match="key too long"):
            validate_dict_field(data, "labels")

    def test_validate_dict_rejects_non_dict_input(self):
        """Test that non-dict input raises error."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            validate_dict_field("not-a-dict", "labels")


class TestAlert:
    """Tests for Alert model."""

    def test_alert_from_dict_with_all_fields(self):
        """Test creating Alert from complete dictionary."""
        data = {
            "id": "alert-123",
            "alert_name": "HighCPU",
            "severity": "P1",
            "alert_source": "prometheus",
            "status": "firing",
            "labels": {"env": "prod", "service": "api"},
            "annotations": {"description": "CPU usage is high"},
            "starts_at": "2026-04-01T10:00:00Z",
            "ends_at": "2026-04-01T11:00:00Z",
            "fingerprint": "abc123",
        }

        alert = Alert.from_dict(data)

        assert alert.id == "alert-123"
        assert alert.alert_name == "HighCPU"
        assert alert.severity == Severity.P1
        assert alert.alert_source == "prometheus"
        assert alert.status == "firing"
        assert alert.labels == {"env": "prod", "service": "api"}
        assert alert.annotations == {"description": "CPU usage is high"}
        assert alert.fingerprint == "abc123"
        assert isinstance(alert.starts_at, datetime)
        assert isinstance(alert.ends_at, datetime)

    def test_alert_from_dict_with_minimal_fields(self):
        """Test creating Alert with only required fields."""
        data = {
            "id": "alert-456",
            "alert_name": "ServiceDown",
            "starts_at": "2026-04-01T10:00:00Z",
        }

        alert = Alert.from_dict(data)

        assert alert.id == "alert-456"
        assert alert.alert_name == "ServiceDown"
        assert alert.severity == Severity.P3  # Default
        assert alert.alert_source == "prometheus"  # Default
        assert alert.status == "firing"  # Default
        assert alert.labels == {}
        assert alert.annotations == {}

    def test_alert_from_dict_uses_fingerprint_as_id(self):
        """Test that fingerprint is used as ID if ID is missing."""
        data = {
            "fingerprint": "fp-789",
            "alert_name": "MemoryLeak",
            "starts_at": "2026-04-01T10:00:00Z",
        }

        alert = Alert.from_dict(data)
        assert alert.id == "fp-789"

    def test_alert_from_dict_uses_labels_alertname(self):
        """Test that labels.alertname is used if alert_name is missing."""
        data = {
            "id": "alert-999",
            "labels": {"alertname": "DiskFull"},
            "starts_at": "2026-04-01T10:00:00Z",
        }

        alert = Alert.from_dict(data)
        assert alert.alert_name == "DiskFull"

    def test_alert_from_dict_missing_id_raises_error(self):
        """Test that missing ID and fingerprint raises error."""
        data = {
            "alert_name": "TestAlert",
            "starts_at": "2026-04-01T10:00:00Z",
        }

        with pytest.raises(ValueError, match="must have either 'id' or 'fingerprint'"):
            Alert.from_dict(data)

    def test_alert_from_dict_missing_alert_name_raises_error(self):
        """Test that missing alert_name raises error."""
        data = {
            "id": "alert-000",
            "starts_at": "2026-04-01T10:00:00Z",
        }

        with pytest.raises(ValueError, match="must have either 'alert_name' or 'labels.alertname'"):
            Alert.from_dict(data)

    def test_alert_from_dict_missing_starts_at_raises_error(self):
        """Test that missing starts_at raises error."""
        data = {
            "id": "alert-000",
            "alert_name": "TestAlert",
        }

        with pytest.raises(ValueError, match="missing required field 'starts_at'"):
            Alert.from_dict(data)

    def test_alert_from_dict_invalid_severity_uses_fallback(self):
        """Test that invalid severity falls back to P3."""
        data = {
            "id": "alert-111",
            "alert_name": "TestAlert",
            "severity": "INVALID",
            "starts_at": "2026-04-01T10:00:00Z",
        }

        alert = Alert.from_dict(data)
        assert alert.severity == Severity.P3

    def test_alert_from_dict_invalid_ends_at_is_ignored(self):
        """Test that invalid ends_at is ignored (not required)."""
        data = {
            "id": "alert-222",
            "alert_name": "TestAlert",
            "starts_at": "2026-04-01T10:00:00Z",
            "ends_at": "invalid-timestamp",
        }

        alert = Alert.from_dict(data)
        assert alert.ends_at is None


class TestAlertGroup:
    """Tests for AlertGroup model."""

    def test_alert_group_creation(self):
        """Test creating an AlertGroup."""
        group = AlertGroup(
            id=1,
            group_name="High CPU Group",
            severity=Severity.P2,
            status="active",
        )

        assert group.id == 1
        assert group.group_name == "High CPU Group"
        assert group.severity == Severity.P2
        assert group.status == "active"
        assert group.get_alert_count() == 0

    def test_add_alert_to_group(self):
        """Test adding an alert to a group."""
        group = AlertGroup(
            id=1,
            group_name="Test Group",
            severity=Severity.P3,
            status="active",
        )

        alert_data = {
            "id": "alert-1",
            "alert_name": "TestAlert",
            "severity": "P2",
            "starts_at": "2026-04-01T10:00:00Z",
        }
        alert = Alert.from_dict(alert_data)

        group.add_alert(alert)

        assert group.get_alert_count() == 1
        assert alert.group_id == 1
        assert group.severity == Severity.P2  # Upgraded to higher severity

    def test_add_multiple_alerts_updates_severity(self):
        """Test that adding alerts updates group severity to highest."""
        group = AlertGroup(
            id=1,
            group_name="Test Group",
            severity=Severity.P3,
            status="active",
        )

        alert1 = Alert.from_dict({
            "id": "alert-1",
            "alert_name": "Alert1",
            "severity": "P2",
            "starts_at": "2026-04-01T10:00:00Z",
        })

        alert2 = Alert.from_dict({
            "id": "alert-2",
            "alert_name": "Alert2",
            "severity": "P1",
            "starts_at": "2026-04-01T10:05:00Z",
        })

        group.add_alert(alert1)
        assert group.severity == Severity.P2

        group.add_alert(alert2)
        assert group.severity == Severity.P1  # Highest priority
        assert group.get_alert_count() == 2


class TestGroupingDecision:
    """Tests for GroupingDecision model."""

    def test_grouping_decision_to_dict(self):
        """Test converting GroupingDecision to dictionary."""
        decision = GroupingDecision(
            action=GroupingAction.JOIN_GROUP,
            confidence=0.85,
            reasoning="Similar error patterns",
            group_id=5,
            group_name="Database Errors",
            related_alert_ids=["alert-1", "alert-2"],
        )

        result = decision.to_dict()

        assert result["action"] == "join_group"
        assert result["confidence"] == 0.85
        assert result["reasoning"] == "Similar error patterns"
        assert result["group_id"] == 5
        assert result["group_name"] == "Database Errors"
        assert result["related_alert_ids"] == ["alert-1", "alert-2"]

    def test_grouping_decision_from_dict(self):
        """Test creating GroupingDecision from dictionary."""
        data = {
            "action": "create_new_group",
            "confidence": 0.92,
            "reasoning": "New pattern detected",
            "group_name": "New Issue Group",
            "related_alert_ids": ["alert-3"],
        }

        decision = GroupingDecision.from_dict(data)

        assert decision.action == GroupingAction.CREATE_NEW_GROUP
        assert decision.confidence == 0.92
        assert decision.reasoning == "New pattern detected"
        assert decision.group_name == "New Issue Group"
        assert decision.related_alert_ids == ["alert-3"]



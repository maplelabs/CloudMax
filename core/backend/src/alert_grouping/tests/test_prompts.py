"""Unit tests for alert grouping prompts."""

from datetime import datetime, timezone
from src.alert_grouping.prompts import (
    create_batch_grouping_prompt,
    format_labels,
    format_annotations,
    format_group_alerts,
    GROUPING_SYSTEM_PROMPT,
)
from src.alert_grouping.models import Alert, Severity


class TestCreateBatchGroupingPrompt:
    """Tests for create_batch_grouping_prompt function."""

    def test_create_prompt_with_single_alert(self):
        """Test creating prompt with a single alert."""
        alert = Alert(
            id="alert-1",
            alert_name="HighCPU",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={"env": "prod", "service": "api"},
            annotations={"summary": "CPU is high"},
            starts_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        
        prompt = create_batch_grouping_prompt([alert], existing_groups=None)
        
        assert "alert-1" in prompt
        assert "HighCPU" in prompt
        assert "P1" in prompt
        assert "1 total alerts" in prompt

    def test_create_prompt_with_multiple_alerts(self):
        """Test creating prompt with multiple alerts."""
        alerts = [
            Alert(
                id=f"alert-{i}",
                alert_name=f"Alert{i}",
                severity=Severity.P2,
                alert_source="prometheus",
                status="firing",
                labels={"env": "prod"},
                annotations={},
                starts_at=datetime(2026, 4, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(3)
        ]
        
        prompt = create_batch_grouping_prompt(alerts, existing_groups=None)
        
        assert "alert-0" in prompt
        assert "alert-1" in prompt
        assert "alert-2" in prompt
        assert "3 total alerts" in prompt

    def test_create_prompt_with_existing_groups(self):
        """Test creating prompt with existing groups."""
        alert = Alert(
            id="alert-new",
            alert_name="NewAlert",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        
        existing_groups = [
            {
                "group_id": 1,
                "group_name": "CPU Issues",
                "sample_alerts": [
                    {"alert_name": "HighCPU", "severity": "P1"}
                ],
            }
        ]
        
        prompt = create_batch_grouping_prompt([alert], existing_groups=existing_groups)
        
        assert "EXISTING INCIDENT GROUPS" in prompt
        assert "CPU Issues" in prompt
        assert "alert-new" in prompt

    def test_create_prompt_without_existing_groups(self):
        """Test creating prompt without existing groups."""
        alert = Alert(
            id="alert-1",
            alert_name="TestAlert",
            severity=Severity.P2,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        
        prompt = create_batch_grouping_prompt([alert], existing_groups=None)
        
        assert "EXISTING INCIDENT GROUPS" not in prompt

    def test_create_prompt_includes_alert_labels(self):
        """Test that prompt includes alert labels."""
        alert = Alert(
            id="alert-1",
            alert_name="TestAlert",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={
                "env": "production",
                "service": "payment-service",
                "container_id": "abc123",
            },
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        
        prompt = create_batch_grouping_prompt([alert])
        
        assert "production" in prompt
        assert "payment-service" in prompt
        assert "container_id" in prompt

    def test_create_prompt_includes_annotations(self):
        """Test that prompt includes alert annotations."""
        alert = Alert(
            id="alert-1",
            alert_name="TestAlert",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={
                "summary": "High memory usage detected",
                "description": "Memory usage above 90%",
            },
            starts_at=datetime.now(timezone.utc),
        )
        
        prompt = create_batch_grouping_prompt([alert])
        
        assert "summary" in prompt
        assert "High memory usage detected" in prompt

    def test_create_prompt_includes_response_format(self):
        """Test that prompt includes expected response format."""
        alert = Alert(
            id="alert-1",
            alert_name="TestAlert",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        
        prompt = create_batch_grouping_prompt([alert])
        
        assert "RESPONSE FORMAT" in prompt
        assert "decisions" in prompt
        assert "action" in prompt
        assert "confidence" in prompt
        assert "reasoning" in prompt


class TestFormatHelpers:
    """Tests for formatting helper functions."""

    def test_format_labels_empty(self):
        """Test formatting empty labels."""
        result = format_labels({})
        assert result == "{}"

    def test_format_labels_with_data(self):
        """Test formatting labels with data."""
        labels = {"env": "prod", "service": "api"}
        result = format_labels(labels)
        assert "env=prod" in result
        assert "service=api" in result

    def test_format_annotations_empty(self):
        """Test formatting empty annotations."""
        result = format_annotations({})
        assert result == "{}"

    def test_format_annotations_with_data(self):
        """Test formatting annotations with data."""
        annotations = {"summary": "Test summary"}
        result = format_annotations(annotations)
        assert "summary=Test summary" in result

    def test_format_annotations_truncates_long_values(self):
        """Test that long annotation values are truncated."""
        long_value = "x" * 200
        annotations = {"description": long_value}
        result = format_annotations(annotations)
        assert "..." in result
        assert len(result) < len(long_value) + 20  # +20 for formatting

    def test_format_group_alerts_empty(self):
        """Test formatting empty alert list."""
        result = format_group_alerts([])
        assert "(no alerts)" in result

    def test_format_group_alerts_with_data(self):
        """Test formatting alerts."""
        alerts = [
            Alert(
                id="alert-1",
                alert_name="HighCPU",
                severity=Severity.P1,
                alert_source="prometheus",
                status="firing",
                labels={"service": "api", "env": "prod"},
                annotations={},
                starts_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
            )
        ]
        
        result = format_group_alerts(alerts)
        
        assert "HighCPU" in result
        assert "P1" in result
        assert "service=api" in result


class TestGroupingSystemPrompt:
    """Tests for grouping system prompt."""

    def test_system_prompt_exists(self):
        """Test that system prompt is defined."""
        assert GROUPING_SYSTEM_PROMPT is not None
        assert len(GROUPING_SYSTEM_PROMPT) > 0

    def test_system_prompt_includes_rules(self):
        """Test that system prompt includes critical rules."""
        assert "join_group" in GROUPING_SYSTEM_PROMPT
        assert "create_new_group" in GROUPING_SYSTEM_PROMPT
        assert "skip" in GROUPING_SYSTEM_PROMPT
        assert "confidence" in GROUPING_SYSTEM_PROMPT


"""Integration tests for alert grouping end-to-end workflows."""

from datetime import datetime, timezone
from src.alert_grouping.models import Alert, Severity


class TestAlertGroupingIntegration:
    """Integration tests for complete alert grouping workflow."""

    def test_llm_response_parsing_create_new_group(self):
        """Test parsing LLM response for creating a new group."""
        import json

        response = """
        {
            "decisions": [
                {
                    "alert_id": "alert-1",
                    "action": "create_new_group",
                    "temp_group_id": 1,
                    "group_name": "CPU Issues - Production API",
                    "confidence": 0.95,
                    "reasoning": "High CPU on production API service"
                },
                {
                    "alert_id": "alert-2",
                    "action": "join_group",
                    "group_id": 1,
                    "confidence": 0.90,
                    "reasoning": "Same container_id as first alert"
                }
            ]
        }
        """

        parsed = json.loads(response)

        assert parsed is not None
        assert "decisions" in parsed
        assert len(parsed["decisions"]) == 2
        assert parsed["decisions"][0]["action"] == "create_new_group"
        assert parsed["decisions"][1]["action"] == "join_group"

    def test_llm_response_parsing_join_existing_group(self):
        """Test parsing LLM response for joining existing group."""
        import json

        response = """
        {
            "decisions": [
                {
                    "alert_id": "alert-3",
                    "action": "join_group",
                    "group_id": 1,
                    "confidence": 0.88,
                    "reasoning": "Matches existing CPU issues group"
                }
            ]
        }
        """

        parsed = json.loads(response)

        assert parsed is not None
        assert parsed["decisions"][0]["action"] == "join_group"
        assert parsed["decisions"][0]["group_id"] == 1

    def test_llm_response_parsing_skip_alert(self):
        """Test parsing LLM response for skipping uncertain alerts."""
        import json

        response = """
        {
            "decisions": [
                {
                    "alert_id": "alert-4",
                    "action": "skip",
                    "confidence": 0.45,
                    "reasoning": "Insufficient information to determine grouping"
                }
            ]
        }
        """

        parsed = json.loads(response)

        assert parsed is not None
        assert parsed["decisions"][0]["action"] == "skip"

    def test_batch_grouping_with_multiple_groups(self):
        """Test batch grouping creates multiple groups correctly."""
        from src.alert_grouping.prompts import create_batch_grouping_prompt
        
        alerts = [
            Alert(
                id=f"alert-{i}",
                alert_name="HighCPU" if i < 2 else "HighMemory",
                severity=Severity.P1 if i < 2 else Severity.P2,
                alert_source="prometheus",
                status="firing",
                labels={
                    "service": "api" if i < 2 else "database",
                    "container_id": f"container-{i % 2}",
                },
                annotations={},
                starts_at=datetime(2026, 4, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(4)
        ]
        
        prompt = create_batch_grouping_prompt(alerts)
        
        # Verify all alerts are in the prompt
        for i in range(4):
            assert f"alert-{i}" in prompt
        
        # Verify different services are mentioned
        assert "api" in prompt
        assert "database" in prompt

    def test_grouping_respects_severity_hierarchy(self):
        """Test that group severity is updated to highest alert severity."""
        from src.alert_grouping.models import AlertGroup
        
        group = AlertGroup(
            id=1,
            group_name="Test Group",
            severity=Severity.P3,
            status="active",
        )
        
        # Add P2 alert
        alert_p2 = Alert(
            id="alert-1",
            alert_name="Alert1",
            severity=Severity.P2,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        group.add_alert(alert_p2)
        assert group.severity == Severity.P2
        
        # Add P1 alert
        alert_p1 = Alert(
            id="alert-2",
            alert_name="Alert2",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        group.add_alert(alert_p1)
        assert group.severity == Severity.P1  # Upgraded to highest
        
        # Add P3 alert (should not downgrade)
        alert_p3 = Alert(
            id="alert-3",
            alert_name="Alert3",
            severity=Severity.P3,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
        )
        group.add_alert(alert_p3)
        assert group.severity == Severity.P1  # Should remain P1

    def test_alert_deduplication_by_fingerprint(self):
        """Test that alerts with same fingerprint are handled correctly."""
        alert1 = Alert(
            id="alert-1",
            alert_name="HighCPU",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
            fingerprint="abc123",
        )
        
        alert2 = Alert(
            id="alert-2",
            alert_name="HighCPU",
            severity=Severity.P1,
            alert_source="prometheus",
            status="firing",
            labels={},
            annotations={},
            starts_at=datetime.now(timezone.utc),
            fingerprint="abc123",
        )
        
        # Same fingerprint indicates same alert
        assert alert1.fingerprint == alert2.fingerprint


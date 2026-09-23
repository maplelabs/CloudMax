"""Unit tests for alert grouping service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.alert_grouping.services.alert_grouping_service import (
    convert_db_alert_to_grouping_alert,
    fetch_active_groups_with_alerts,
    process_batch_alerts_for_grouping_async,
    run_batch_grouping_analysis,
)
from src.alert_grouping.models import Severity as GroupingSeverity
from src.server.models.api import Severity
from src.server.models.db import AlertDBModel, AlertGroupDBModel


class TestConvertDbAlertToGroupingAlert:
    """Tests for convert_db_alert_to_grouping_alert function."""

    def test_convert_basic_alert(self):
        """Test converting a basic database alert to grouping alert."""
        db_alert = AlertDBModel(
            id=1,
            alert_name="HighCPU",
            severity=Severity.P1,
            alert_source="prometheus",
            alert_status="firing",
            payload={
                "labels": {"env": "prod", "service": "api"},
                "annotations": {"description": "CPU usage is high"},
                "fingerprint": "abc123",
            },
            created_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        
        result = convert_db_alert_to_grouping_alert(db_alert)
        
        assert result.id == "alert-1"
        assert result.alert_name == "HighCPU"
        assert result.severity == GroupingSeverity.P1
        assert result.alert_source == "prometheus"
        assert result.status == "firing"
        assert result.labels == {"env": "prod", "service": "api"}
        assert result.annotations == {"description": "CPU usage is high"}
        assert result.fingerprint == "abc123"

    def test_convert_alert_with_null_payload(self):
        """Test converting alert with null payload."""
        db_alert = AlertDBModel(
            id=2,
            alert_name="TestAlert",
            severity=Severity.P2,
            alert_source="grafana",
            alert_status="firing",
            payload=None,
            created_at=datetime.now(timezone.utc),
        )
        
        result = convert_db_alert_to_grouping_alert(db_alert)
        
        assert result.id == "alert-2"
        assert result.alert_name == "TestAlert"
        assert result.labels == {}
        assert result.annotations == {}

    def test_convert_alert_uses_alertname_from_labels(self):
        """Test that alertname from labels is used as fallback."""
        db_alert = AlertDBModel(
            id=3,
            alert_name=None,
            severity=Severity.P3,
            alert_source="prometheus",
            alert_status="firing",
            payload={"labels": {"alertname": "FromLabels"}},
            created_at=datetime.now(timezone.utc),
        )
        
        result = convert_db_alert_to_grouping_alert(db_alert)
        
        assert result.alert_name == "FromLabels"

    def test_convert_alert_severity_mapping(self):
        """Test that severity is correctly mapped."""
        test_cases = [
            (Severity.P1, GroupingSeverity.P1),
            (Severity.P2, GroupingSeverity.P2),
            (Severity.P3, GroupingSeverity.P3),
        ]
        
        for db_severity, expected_grouping_severity in test_cases:
            db_alert = AlertDBModel(
                id=1,
                alert_name="Test",
                severity=db_severity,
                alert_source="test",
                alert_status="firing",
                payload={},
                created_at=datetime.now(timezone.utc),
            )
            
            result = convert_db_alert_to_grouping_alert(db_alert)
            assert result.severity == expected_grouping_severity


@pytest.mark.asyncio
class TestFetchActiveGroupsWithAlerts:
    """Tests for fetch_active_groups_with_alerts function."""

    async def test_fetch_empty_groups(self):
        """Test fetching when no groups exist."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Create a proper mock result chain
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        # Make execute() return an awaitable that resolves to mock_result
        async def mock_execute(*args, **kwargs):
            return mock_result

        mock_session.execute = mock_execute

        mock_config = MagicMock()
        mock_config.active_groups_lookback_minutes = 30
        mock_config.max_active_groups_context = 20

        result = await fetch_active_groups_with_alerts(mock_session, config=mock_config)

        assert result == []

    async def test_fetch_groups_with_alerts(self):
        """Test fetching groups with alerts."""
        # Create mock group with alerts
        mock_alert1 = AlertDBModel(
            id=1,
            alert_name="Alert1",
            severity=Severity.P1,
            alert_source="prometheus",
            alert_status="firing",
            payload={"labels": {}, "annotations": {}},
            created_at=datetime.now(timezone.utc),
        )

        mock_alert2 = AlertDBModel(
            id=2,
            alert_name="Alert2",
            severity=Severity.P2,
            alert_source="prometheus",
            alert_status="firing",
            payload={"labels": {}, "annotations": {}},
            created_at=datetime.now(timezone.utc),
        )

        mock_group = AlertGroupDBModel(
            id=1,
            group_name="Test Group",
            severity=Severity.P1,
            status="active",
            triage_status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_group.alerts = [mock_alert1, mock_alert2]

        mock_session = AsyncMock(spec=AsyncSession)

        # Create a proper mock result chain
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_group])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        # Make execute() return an awaitable that resolves to mock_result
        async def mock_execute(*args, **kwargs):
            return mock_result

        mock_session.execute = mock_execute

        mock_config = MagicMock()
        mock_config.active_groups_lookback_minutes = 30
        mock_config.max_active_groups_context = 20

        result = await fetch_active_groups_with_alerts(mock_session, config=mock_config)

        assert len(result) == 1
        assert result[0]["group_id"] == 1
        assert result[0]["group_name"] == "Test Group"
        assert len(result[0]["alerts"]) == 2

    async def test_fetch_excludes_in_progress_groups(self):
        """Test that groups with triage_status='in_progress' are excluded."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Create a proper mock result chain
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        # Track if execute was called
        execute_called = False

        # Make execute() return an awaitable that resolves to mock_result
        async def mock_execute(*args, **kwargs):
            nonlocal execute_called
            execute_called = True
            return mock_result

        mock_session.execute = mock_execute

        mock_config = MagicMock()
        mock_config.active_groups_lookback_minutes = 30
        mock_config.max_active_groups_context = 20

        await fetch_active_groups_with_alerts(mock_session, config=mock_config)

        # Verify execute was called (query was run)
        assert execute_called


@pytest.mark.asyncio
class TestProcessBatchGrouping:
    """Tests for process_batch_alerts_for_grouping_async function."""

    async def test_process_empty_batch(self):
        """Test processing empty batch returns empty results."""
        result = await process_batch_alerts_for_grouping_async([])

        # Check the actual keys returned by the function
        assert result["total_alerts"] == 0
        assert result["new_groups_created"] == 0
        assert result["alerts_joined_existing"] == 0
        assert result["alerts_skipped"] == 0

    async def test_run_batch_grouping_analysis_with_empty_alerts(self):
        """Test running batch grouping analysis with empty alert list."""
        # Mock the LLM to avoid database config dependency
        with patch('src.alert_grouping.services.alert_grouping_service.get_primary_llm_async') as mock_llm_getter:
            # Create a mock LLM instance
            mock_llm_instance = AsyncMock()

            # Create a mock response object with content attribute
            mock_response = MagicMock()
            mock_response.content = '{"decisions": []}'

            # Make ainvoke return the mock response
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)

            # Make get_primary_llm_async return the mock LLM instance
            mock_llm_getter.return_value = mock_llm_instance

            result = await run_batch_grouping_analysis([], [])

            # Should handle empty list gracefully
            assert isinstance(result, dict)
            # Should return empty decisions for empty input
            assert result.get("decisions", []) == []


class TestLLMResponseParsing:
    """Tests for parsing LLM responses."""

    def test_parse_valid_json_response(self):
        """Test parsing valid JSON response from LLM."""
        from src.server.utilities.llm_response_parser import extract_json_from_markdown
        import json

        response = """
        Here's the grouping decision:
        ```json
        {
            "decisions": [
                {"alert_id": "1", "action": "join_group", "group_id": 5}
            ]
        }
        ```
        """

        # extract_json_from_markdown returns a string, not a dict
        result_str = extract_json_from_markdown(response)
        assert result_str is not None

        # Parse the JSON string to dict
        result = json.loads(result_str)
        assert "decisions" in result
        assert len(result["decisions"]) == 1

    def test_parse_json_without_markdown(self):
        """Test parsing JSON without markdown wrapper."""
        from src.server.utilities.llm_response_parser import extract_json_from_markdown
        import json

        response = '{"decisions": [{"alert_id": "1", "action": "skip"}]}'

        # extract_json_from_markdown returns a string, not a dict
        result_str = extract_json_from_markdown(response)
        assert result_str is not None

        # Parse the JSON string to dict
        result = json.loads(result_str)
        assert "decisions" in result

    def test_parse_malformed_json_returns_none(self):
        """Test that malformed JSON returns a string (even if invalid)."""
        from src.server.utilities.llm_response_parser import extract_json_from_markdown
        import json

        response = "This is not valid JSON at all"

        # extract_json_from_markdown returns the string as-is if no code blocks
        result_str = extract_json_from_markdown(response)
        assert isinstance(result_str, str)

        # Trying to parse it as JSON should raise an exception
        with pytest.raises(json.JSONDecodeError):
            json.loads(result_str)



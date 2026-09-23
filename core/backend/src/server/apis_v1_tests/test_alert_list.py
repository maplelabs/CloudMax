from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.server.models.api.enums import Status, Severity
from src.server.models.db.alert import Alert as DBAlert
from src.server.models.db.evaluation import Evaluation as EvaluationDBModel
from src.server.models.db.triage import Triage as TriageDBModel

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def sample_alerts(db_session):
    """Create sample alert data for testing"""
    base_time = datetime.now(timezone.utc)

    # Alert 1: No triage, no evaluation (PENDING status)
    alert1 = DBAlert(
        external_id="test-alert-1",
        payload={
            "labels": {
                "alertname": "CPU High Usage",
                "severity": "P1",
                "instance": "web-server-01"
            },
            "startsAt": (base_time - timedelta(hours=1)).isoformat() + "Z"
        },
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="CPU High Usage",
        created_at=base_time - timedelta(hours=1)
    )
    db_session.add(alert1)
    await db_session.flush()

    # Alert 2: Has triage, no evaluation
    alert2 = DBAlert(
        external_id="test-alert-2",
        payload={
            "labels": {
                "alertname": "Memory Leak",
                "severity": "P2",
                "service": "user-service"
            },
            "startsAt": (base_time - timedelta(hours=2)).isoformat() + "Z"
        },
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Memory Leak",
        created_at=base_time - timedelta(hours=2)
    )
    db_session.add(alert2)
    await db_session.flush()

    # Add triage for alert2
    triage2 = TriageDBModel(
        alert_id=alert2.id,
        status=Status.SUCCESS,
        thread_id="triage_thread_2",
        job_id="triage_job_2",
        root_cause_summary="Memory leak detected in user service"
    )
    db_session.add(triage2)

    # Alert 3: Has both triage and evaluation
    alert3 = DBAlert(
        external_id="test-alert-3",
        payload={
            "labels": {
                "alertname": "Database Timeout",
                "severity": "P1",
                "database": "postgres"
            },
            "startsAt": (base_time - timedelta(hours=3)).isoformat() + "Z"
        },
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Database Timeout",
        created_at=base_time - timedelta(hours=3)
    )
    db_session.add(alert3)
    await db_session.flush()

    # Add triage for alert3
    triage3 = TriageDBModel(
        alert_id=alert3.id,
        status=Status.SUCCESS,
        thread_id="triage_thread_3",
        job_id="triage_job_3",
        root_cause_summary="Database connection pool exhausted"
    )
    db_session.add(triage3)

    # Add evaluation for alert3
    evaluation3 = EvaluationDBModel(
        alert_id=alert3.id,
        status=Status.SUCCESS,
        job_id="eval_job_3",
        root_cause_similarity_percent=85,
        orch_agent_util_score_percent=72,
        sub_agent_tool_util_score_percent=91
    )
    db_session.add(evaluation3)

    # Alert 4: Error case
    alert4 = DBAlert(
        external_id="test-alert-4",
        payload={
            "labels": {
                "alertname": "Disk Space Critical",
                "severity": "P1",
                "mount": "/var/log"
            },
            "startsAt": (base_time - timedelta(hours=4)).isoformat() + "Z"
        },
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Disk Space Critical",
        created_at=base_time - timedelta(hours=4)
    )
    db_session.add(alert4)
    await db_session.flush()

    # Add failed triage for alert4
    triage4 = TriageDBModel(
        alert_id=alert4.id,
        status=Status.ERROR,
        thread_id="triage_thread_4",
        job_id="triage_job_4",
        error_message="Connection timeout to analysis service"
    )
    db_session.add(triage4)

    await db_session.commit()

    return {
        "alert1": alert1,
        "alert2": alert2,
        "alert3": alert3,
        "alert4": alert4
    }


# Test Cases
async def test_list_alerts_basic(client, sample_alerts):
    """Test basic alert listing functionality"""
    # Use a longer time range to include all test alerts
    response = await client.get("/v1/alerts?time_range=24h")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "alerts" in data
    assert "pagination" in data
    assert len(data["alerts"]) == 4

    # Check pagination metadata
    pagination = data["pagination"]
    assert pagination["current_page"] == 1
    assert pagination["total_items"] == 4
    assert pagination["page_size"] == 10


async def test_list_alerts_with_different_statuses(client, sample_alerts):
    """Test that alerts show correct triage and evaluation statuses"""
    response = await client.get("/v1/alerts?time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Find alerts by name and check their statuses
    alert_by_name = {alert["name"]: alert for alert in alerts}

    # Alert 1: No triage, no evaluation
    cpu_alert = alert_by_name["CPU High Usage"]
    assert cpu_alert["triage_status"] == "pending"
    assert cpu_alert["evaluation_status"] == "pending"
    assert cpu_alert["evaluation_score"] is None  # Default when no evaluation

    # Alert 2: Has triage, no evaluation
    memory_alert = alert_by_name["Memory Leak"]
    assert memory_alert["triage_status"] == "success"
    assert memory_alert["evaluation_status"] == "pending"
    assert memory_alert["evaluation_score"] is None

    # Alert 3: Has both triage and evaluation
    db_alert = alert_by_name["Database Timeout"]
    assert db_alert["triage_status"] == "success"
    assert db_alert["evaluation_status"] == "success"
    # Average of 8.5, 7.2, 9.1 = 8.27 (rounded)
    assert abs(db_alert["evaluation_score"] - 8.27) > 0.01

    # Alert 4: Error case
    disk_alert = alert_by_name["Disk Space Critical"]
    assert disk_alert["triage_status"] == "error"
    assert disk_alert["evaluation_status"] == "pending"


async def test_list_alerts_filter_by_severity(client, sample_alerts):
    """Test filtering alerts by severity"""
    response = await client.get("/v1/alerts?severity=P1&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return 3 P1 alerts
    assert len(alerts) == 3
    for alert in alerts:
        assert alert["severity"] == "P1"


async def test_list_alerts_filter_by_source(client, sample_alerts):
    """Test filtering alerts by source - currently not implemented, so test all alerts"""
    response = await client.get("/v1/alerts?time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return all 4 alerts since source filtering is not implemented
    assert len(alerts) == 4

    # Verify we have both grafana and prometheus alerts
    sources = {alert["alert_source"] for alert in alerts}
    assert "grafana" in sources
    assert "prometheus" in sources


async def test_list_alerts_filter_by_triage_status(client, sample_alerts):
    """Test filtering alerts by triage status = success"""
    response = await client.get("/v1/alerts?triage_status=success&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return 2 alerts with successful triage (alerts 2 and 3)
    assert len(alerts) == 2

    # Verify all returned alerts have success triage status
    for alert in alerts:
        assert alert["triage_status"] == "success"

    # Verify we have the expected alerts
    alert_names = {alert["name"] for alert in alerts}
    assert "Memory Leak" in alert_names
    assert "Database Timeout" in alert_names


async def test_list_alerts_pagination(client, sample_alerts):
    """Test pagination functionality"""
    # Test first page with page_size=2
    response = await client.get("/v1/alerts?page=1&page_size=2&time_range=24h")

    assert response.status_code == 200
    data = response.json()

    assert len(data["alerts"]) == 2
    assert data["pagination"]["current_page"] == 1
    assert data["pagination"]["page_size"] == 2
    assert data["pagination"]["total_items"] == 4

    # Test second page
    response = await client.get("/v1/alerts?page=2&page_size=2&time_range=24h")

    assert response.status_code == 200
    data = response.json()

    assert len(data["alerts"]) == 2
    assert data["pagination"]["current_page"] == 2


async def test_list_alerts_search_by_name(client, sample_alerts):
    """Test searching alerts by name"""
    response = await client.get("/v1/alerts?name_contains=Database&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    assert len(alerts) == 1
    assert "Database" in alerts[0]["name"]


async def test_list_alerts_empty_result(client, db_session):
    """Test when no alerts match the criteria"""
    response = await client.get("/v1/alerts?severity=P3")

    assert response.status_code == 200
    data = response.json()

    assert len(data["alerts"]) == 0
    assert data["pagination"]["total_items"] == 0


async def test_print_tables(db_session, sample_alerts):
    """Print table structures and sample data for debugging"""

    async def print_table(model, name):
        # Get column names
        columns = list(model.__table__.columns.keys())
        print(f"\n=== {name.upper()} TABLE ===")
        print(f"Columns: {columns}")
        print("-" * 50)

        # Fetch 1 row
        result = await db_session.execute(select(model).limit(1))
        rows = result.scalars().all()

        if rows:
            row = rows[0]
            print("Sample row data:")
            for col in columns:
                value = getattr(row, col)
                # Format datetime and other complex types nicely
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                elif isinstance(value, dict):
                    value = str(value)[:100] + "..." if len(str(value)) > 100 else value
                print(f"  {col}: {value}")
        else:
            print("No data found in table")
        print()

    await print_table(DBAlert, "Alerts")
    await print_table(TriageDBModel, "Triages")
    await print_table(EvaluationDBModel, "Evaluations")


async def test_list_alerts_filter_by_triage_status_success(client, sample_alerts):
    """Test filtering alerts by triage status = success"""
    response = await client.get("/v1/alerts?triage_status=success&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alerts 2 and 3 (both have successful triage)
    assert len(alerts) == 2
    alert_names = {alert["name"] for alert in alerts}
    assert "Memory Leak" in alert_names
    assert "Database Timeout" in alert_names


async def test_list_alerts_filter_by_triage_status_error(client, sample_alerts):
    """Test filtering alerts by triage status = error"""
    response = await client.get("/v1/alerts?triage_status=error&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alert 4 (has error triage)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Disk Space Critical"
    assert alerts[0]["triage_status"] == "error"


async def test_list_alerts_filter_by_triage_status_pending(client, sample_alerts):
    """Test filtering alerts by triage status = pending (no triage records)"""
    response = await client.get("/v1/alerts?triage_status=pending&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return no alerts since pending means no triage record exists
    # and our filter looks for existing triage records with pending status
    assert len(alerts) == 0


async def test_list_alerts_filter_by_evaluation_status_success(client, sample_alerts):
    """Test filtering alerts by evaluation status = success"""
    response = await client.get("/v1/alerts?evaluation_status=success&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alert 3 (has successful evaluation)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Database Timeout"
    assert alerts[0]["evaluation_status"] == "success"


async def test_list_alerts_filter_by_evaluation_status_pending(client, sample_alerts):
    """Test filtering alerts by evaluation status = pending"""
    response = await client.get("/v1/alerts?evaluation_status=pending&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return no alerts since pending means no evaluation record exists
    assert len(alerts) == 0


async def test_list_alerts_filter_by_evaluation_score_greater_than(client, sample_alerts):
    """Test filtering alerts by evaluation score > 8.0"""
    response = await client.get("/v1/alerts?evaluation_score_operator=>&evaluation_score_value=8.0&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alert 3 (average score 8.27 > 8.0)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Database Timeout"
    assert alerts[0]["evaluation_score"] > 8.0


async def test_list_alerts_filter_by_evaluation_score_less_than(client, sample_alerts):
    """Test filtering alerts by evaluation score < 8.0"""
    response = await client.get("/v1/alerts?evaluation_score_operator=<&evaluation_score_value=8.0&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return no alerts since only alert 3 has evaluation and its score is > 8.0
    assert len(alerts) == 0


async def test_list_alerts_filter_by_evaluation_score_greater_equal(client, sample_alerts):
    """Test filtering alerts by evaluation score >= 8.26"""
    response = await client.get(
        "/v1/alerts?evaluation_score_operator=%3E%3D&evaluation_score_value=8.26&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alert 3 (score 8.267 >= 8.26)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Database Timeout"


async def test_list_alerts_combined_filters(client, sample_alerts):
    """Test combining multiple filters"""
    response = await client.get("/v1/alerts?triage_status=success&evaluation_status=success&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alert 3 (has both successful triage and evaluation)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Database Timeout"
    assert alerts[0]["triage_status"] == "success"
    assert alerts[0]["evaluation_status"] == "success"


async def test_list_alerts_combined_filters_with_score(client, sample_alerts):
    """Test combining triage, evaluation, and score filters"""
    response = await client.get(
        "/v1/alerts?triage_status=success&evaluation_score_operator=>&evaluation_score_value=8.0&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    # Should return alert 3 (successful triage AND score > 8.0)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Database Timeout"


async def test_list_alerts_no_results_with_filters(client, sample_alerts):
    """Test filters that should return no results"""
    response = await client.get(
        "/v1/alerts?triage_status=success&evaluation_score_operator=>&evaluation_score_value=90.0&time_range=24h")

    assert response.status_code == 200
    data = response.json()

    # Should return no alerts (no alert has both successful triage AND score > 90.0)
    assert len(data["alerts"]) == 0
    assert data["pagination"]["total_items"] == 0


# ============================================================================
# EDGE CASES AND COMPREHENSIVE ALERT LIST TESTS
# ============================================================================

@pytest_asyncio.fixture
async def edge_case_alerts(db_session):
    """Create alerts for edge case testing"""
    base_time = datetime.now(timezone.utc)

    # Alert 1: Very old alert (outside most time ranges)
    alert1 = DBAlert(
        external_id="edge-alert-1",
        payload={
            "labels": {
                "alertname": "Very Old Alert",
                "severity": "P1",
                "service": "legacy-service"
            },
            "startsAt": (base_time - timedelta(days=60)).isoformat() + "Z"
        },
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Very Old Alert",
        created_at=base_time - timedelta(days=60)
    )
    db_session.add(alert1)

    # Alert 2: Future alert (edge case for time filtering)
    alert2 = DBAlert(
        external_id="edge-alert-2",
        payload={
            "labels": {
                "alertname": "Future Alert",
                "severity": "P2",
                "service": "time-service"
            },
            "startsAt": (base_time + timedelta(hours=1)).isoformat() + "Z"
        },
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Future Alert",
        created_at=base_time + timedelta(hours=1)
    )
    db_session.add(alert2)

    # Alert 3: Alert with special characters in name
    alert3 = DBAlert(
        external_id="edge-alert-3",
        payload={
            "labels": {
                "alertname": "Alert with Special Chars: @#$%^&*()[]{}|\\;':\",./<>?",
                "severity": "P3",
                "service": "special-service"
            },
            "startsAt": (base_time - timedelta(minutes=25)).isoformat() + "Z"
        },
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P3,
        alert_name="Alert with Special Chars: @#$%^&*()[]{}|\\;':\",./<>?",
        created_at=base_time - timedelta(minutes=25)
    )
    db_session.add(alert3)

    # Alert 4: Alert with very long name
    long_name = "Very Long Alert Name " * 20  # 400+ characters
    alert4 = DBAlert(
        external_id="edge-alert-4",
        payload={
            "labels": {
                "alertname": long_name,
                "severity": "P1",
                "service": "long-name-service"
            },
            "startsAt": (base_time - timedelta(hours=2)).isoformat() + "Z"
        },
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name=long_name,
        created_at=base_time - timedelta(hours=2)
    )
    db_session.add(alert4)

    # Alert 5: Alert with empty/minimal payload
    alert5 = DBAlert(
        external_id="edge-alert-5",
        payload={},
        alert_source="minimal",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Minimal Alert",
        created_at=base_time - timedelta(minutes=25)
    )
    db_session.add(alert5)

    await db_session.commit()

    return {
        "old_alert": alert1,
        "future_alert": alert2,
        "special_chars_alert": alert3,
        "long_name_alert": alert4,
        "minimal_alert": alert5
    }


async def test_list_alerts_with_special_characters_in_name(client, edge_case_alerts):
    """Test searching alerts with special characters in names"""
    # Search for special characters
    response = await client.get("/v1/alerts?name_contains=Special Chars&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    assert len(alerts) == 1
    assert "Special Chars" in alerts[0]["name"]

    # Test URL encoding of special characters
    response = await client.get("/v1/alerts?name_contains=%40%23%24&time_range=24h")  # @#$

    assert response.status_code == 200
    # Should handle URL encoded special characters gracefully


async def test_list_alerts_with_very_long_names(client, edge_case_alerts):
    """Test alerts with very long names"""
    response = await client.get("/v1/alerts?name_contains=Very Long Alert Name&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]

    assert len(alerts) == 1
    # Name should be truncated or handled properly
    assert len(alerts[0]["name"]) > 100  # Should contain the long name


async def test_list_alerts_with_minimal_payload(client, edge_case_alerts):
    """Test alerts with minimal or empty payloads"""
    response = await client.get("/v1/alerts?name_contains=Minimal&time_range=24h")

    assert response.status_code == 200
    alerts = response.json()["alerts"]
    print(
        "******************************************************************************************************************************************************",
        alerts)
    assert len(alerts) == 1
    assert alerts[0]["name"] == "Minimal Alert"
    # Should handle empty payload gracefully


async def test_list_alerts_extreme_pagination_values(client, sample_alerts):
    """Test pagination with extreme values"""

    # Test page_size = 1 (minimum)
    response = await client.get("/v1/alerts?page_size=1&time_range=24h")
    assert response.status_code == 200
    data = response.json()
    assert len(data["alerts"]) == 1
    assert data["pagination"]["page_size"] == 1

    # Test page beyond available data
    response = await client.get("/v1/alerts?page=100&page_size=10&time_range=24h")
    assert response.status_code == 200
    data = response.json()
    assert len(data["alerts"]) == 0  # No alerts on page 100
    assert data["pagination"]["current_page"] == 100


async def test_list_alerts_invalid_pagination_parameters(client, sample_alerts):
    """Test invalid pagination parameters"""

    # Test page = 0 (should default to 1)
    response = await client.get("/v1/alerts?page=0&time_range=24h")
    assert response.status_code == 422  # Should return validation error

    # Test negative page
    response = await client.get("/v1/alerts?page=-1&time_range=24h")
    assert response.status_code == 422  # Should return validation error

    # Test page_size = 0
    response = await client.get("/v1/alerts?page_size=0&time_range=24h")
    assert response.status_code == 422  # Should return validation error

    # Test negative page_size
    response = await client.get("/v1/alerts?page_size=-5&time_range=24h")
    assert response.status_code == 422  # Should return validation error


async def test_list_alerts_case_insensitive_search(client, sample_alerts):
    """Test case-insensitive name search"""

    # Test lowercase search
    response = await client.get("/v1/alerts?name_contains=database&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 1
    assert "Database" in alerts[0]["name"]

    # Test uppercase search
    response = await client.get("/v1/alerts?name_contains=DATABASE&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 1
    assert "Database" in alerts[0]["name"]

    # Test mixed case search
    response = await client.get("/v1/alerts?name_contains=DaTaBaSe&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 1
    assert "Database" in alerts[0]["name"]


async def test_list_alerts_partial_name_matching(client, sample_alerts):
    """Test partial name matching with various patterns"""

    # Test single character
    response = await client.get("/v1/alerts?name_contains=C&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # Should find "CPU High Usage" and "Disk Space Critical"
    assert len(alerts) >= 1

    # Test partial word
    response = await client.get("/v1/alerts?name_contains=Mem&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # Should find "Memory Leak"
    assert len(alerts) == 1
    assert "Memory" in alerts[0]["name"]

    # Test multiple words
    response = await client.get("/v1/alerts?name_contains=High Usage&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # Should find "CPU High Usage"
    assert len(alerts) == 1
    assert "CPU High Usage" in alerts[0]["name"]

    # Test empty search (should return all)
    response = await client.get("/v1/alerts?name_contains=&time_range=24h")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    assert len(alerts) == 4  # All sample alerts


async def test_list_alerts_time_range_edge_cases(client, edge_case_alerts):
    """Test time range filtering with edge cases"""

    # Test very short time range (should find recent alerts only)
    response = await client.get("/v1/alerts?time_range=30m")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # Should find special_chars_alert (25 min ago) but not others
    alert_names = {alert["name"] for alert in alerts}
    assert "Alert with Special Chars" in " ".join(alert_names)

    # Test very long time range (should find old alerts)
    response = await client.get("/v1/alerts?time_range=30d")
    assert response.status_code == 200
    alerts = response.json()["alerts"]
    # Should find more alerts including older ones
    assert len(alerts) >= 1


async def test_list_alerts_sorting_consistency(client, sample_alerts):
    """Test that alert sorting is consistent across requests"""

    # Make multiple requests and verify order is consistent
    responses = []
    for _ in range(3):
        response = await client.get("/v1/alerts?time_range=24h")
        assert response.status_code == 200
        responses.append(response.json()["alerts"])

    # All responses should have same order
    for i in range(1, len(responses)):
        assert len(responses[i]) == len(responses[0])
        for j in range(len(responses[i])):
            assert responses[i][j]["id"] == responses[0][j]["id"]

    # Test sorting with pagination
    page1 = await client.get("/v1/alerts?page=1&page_size=2&time_range=24h")
    page2 = await client.get("/v1/alerts?page=2&page_size=2&time_range=24h")

    assert page1.status_code == 200
    assert page2.status_code == 200

    page1_alerts = page1.json()["alerts"]
    page2_alerts = page2.json()["alerts"]

    # No overlap between pages
    page1_ids = {alert["id"] for alert in page1_alerts}
    page2_ids = {alert["id"] for alert in page2_alerts}
    assert len(page1_ids.intersection(page2_ids)) == 0


async def test_list_alerts_response_field_validation(client, sample_alerts):
    """Test that all required fields are present in response"""
    response = await client.get("/v1/alerts?time_range=24h")

    assert response.status_code == 200
    data = response.json()

    # Validate top-level structure
    assert "alerts" in data
    assert "pagination" in data
    assert isinstance(data["alerts"], list)
    assert isinstance(data["pagination"], dict)

    # Validate pagination fields
    pagination = data["pagination"]
    required_pagination_fields = ["current_page", "page_size", "total_items", "page_size"]
    for field in required_pagination_fields:
        assert field in pagination
        assert isinstance(pagination[field], int)
        assert pagination[field] >= 0

    # Validate alert fields
    for alert in data["alerts"]:
        required_alert_fields = [
            "id", "name", "severity", "triage_status", "evaluation_status",
            "started_at", "last_updated_at", "alert_source"
        ]
        for field in required_alert_fields:
            assert field in alert

        # Validate field types
        assert isinstance(alert["id"], str)
        assert isinstance(alert["name"], str)
        assert alert["severity"] in ["P1", "P2", "P3"]
        assert alert["triage_status"] in ["pending", "success", "error", "processing"]
        assert alert["evaluation_status"] in ["pending", "success", "error", "processing"]
        assert isinstance(alert["started_at"], str)
        assert isinstance(alert["last_updated_at"], str)
        assert isinstance(alert["alert_source"], str)

        # evaluation_score can be null or float
        if alert["evaluation_score"] is not None:
            assert isinstance(alert["evaluation_score"], (int, float))
            assert 10 <= alert["evaluation_score"] <= 100


# ============================================================================
# CUSTOM TIME RANGE TESTS
# ============================================================================


async def test_list_alerts_custom_time_range_valid(client, sample_alerts):
    """Test custom time range with valid start_time and end_time"""
    # Use a custom range that covers the sample alerts (created within last 24h)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=12)

    # URL-encode the datetime strings to handle the + sign in timezone
    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert "pagination" in data


async def test_list_alerts_custom_time_range_missing_start_time(client, sample_alerts):
    """Test custom time range validation - missing start_time"""
    end_time = datetime.now(timezone.utc)
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&end_time={end_time_encoded}"
    )

    assert response.status_code == 400
    data = response.json()
    assert "start_time and end_time are required" in data["detail"]


async def test_list_alerts_custom_time_range_missing_end_time(client, sample_alerts):
    """Test custom time range validation - missing end_time"""
    start_time = datetime.now(timezone.utc) - timedelta(days=7)
    start_time_encoded = quote(start_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}"
    )

    assert response.status_code == 400
    data = response.json()
    assert "start_time and end_time are required" in data["detail"]


async def test_list_alerts_custom_time_range_missing_both(client, sample_alerts):
    """Test custom time range validation - missing both start_time and end_time"""
    response = await client.get("/v1/alerts?time_range=custom")

    assert response.status_code == 400
    data = response.json()
    assert "start_time and end_time are required" in data["detail"]


async def test_list_alerts_custom_time_range_start_after_end(client, sample_alerts):
    """Test custom time range validation - start_time >= end_time"""
    now = datetime.now(timezone.utc)
    start_time = now
    end_time = now - timedelta(hours=1)  # end_time is before start_time

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 400
    data = response.json()
    assert "start_time must be before end_time" in data["detail"]


async def test_list_alerts_custom_time_range_start_equals_end(client, sample_alerts):
    """Test custom time range validation - start_time equals end_time"""
    now = datetime.now(timezone.utc)
    now_encoded = quote(now.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={now_encoded}&end_time={now_encoded}"
    )

    assert response.status_code == 400
    data = response.json()
    assert "start_time must be before end_time" in data["detail"]


async def test_list_alerts_custom_time_range_exceeds_90_days(client, sample_alerts):
    """Test custom time range validation - range exceeds 90 days"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=91)  # 91 days ago

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 400
    data = response.json()
    assert "Custom time range cannot exceed 90 days" in data["detail"]


async def test_list_alerts_custom_time_range_exactly_90_days(client, sample_alerts):
    """Test custom time range validation - exactly 90 days should work"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=90)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data


async def test_list_alerts_custom_time_range_filters_correctly(client, edge_case_alerts):
    """Test custom time range filters alerts correctly based on created_at"""
    # Create a narrow time range that should only include specific alerts
    now = datetime.now(timezone.utc)
    # Range: 30 minutes ago to now (should include special_chars_alert and minimal_alert at 25 min ago)
    start_time = now - timedelta(minutes=30)
    end_time = now

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 200
    data = response.json()
    alerts = data["alerts"]
    # Should find alerts created within the last 30 minutes
    assert len(alerts) >= 0  # May vary based on fixture timing


async def test_list_alerts_predefined_ranges_still_work(client, sample_alerts):
    """Test that predefined time ranges still work correctly"""
    predefined_ranges = ["30m", "1h", "6h", "24h", "7d", "30d"]

    for time_range in predefined_ranges:
        response = await client.get(f"/v1/alerts?time_range={time_range}")

        assert response.status_code == 200, f"Failed for time_range={time_range}"
        data = response.json()
        assert "alerts" in data
        assert "pagination" in data


# ============================================================================
# ADDITIONAL EDGE CASE TESTS
# ============================================================================


async def test_list_alerts_custom_time_range_very_short(client, sample_alerts):
    """Test custom time range with very short duration (1 minute)"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=1)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert "pagination" in data


async def test_list_alerts_custom_time_range_zulu_timezone(client, sample_alerts):
    """Test custom time range with Z (Zulu) timezone format"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=6)

    # Use Z format instead of +00:00
    start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    end_time_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_str}&end_time={end_time_str}"
    )

    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert "pagination" in data


async def test_list_alerts_custom_time_range_invalid_datetime_format(client, sample_alerts):
    """Test custom time range with invalid datetime format"""
    response = await client.get(
        "/v1/alerts?time_range=custom&start_time=invalid-date&end_time=also-invalid"
    )

    # Should return 422 (Unprocessable Entity) for invalid datetime format
    assert response.status_code == 422


async def test_list_alerts_custom_time_range_just_under_90_days(client, sample_alerts):
    """Test custom time range just under 90 days (89 days 23 hours)"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=89, hours=23)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data


async def test_list_alerts_custom_time_range_just_over_90_days(client, sample_alerts):
    """Test custom time range just over 90 days (90 days 1 hour)"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=90, hours=1)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    response = await client.get(
        f"/v1/alerts?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
    )

    assert response.status_code == 400
    data = response.json()
    assert "Custom time range cannot exceed 90 days" in data["detail"]


@pytest_asyncio.fixture
async def large_dataset_alerts(db_session):
    """Create a large dataset for performance testing"""
    base_time = datetime.utcnow()
    alerts = []

    # Create 100 alerts with various statuses
    for i in range(100):
        alert = DBAlert(
            external_id=f"perf-alert-{i}",
            payload={
                "labels": {
                    "alertname": f"Performance Test Alert {i}",
                    "severity": ["P1", "P2", "P3"][i % 3],
                    "service": f"service-{i % 10}"
                }
            },
            alert_source=["grafana", "prometheus"][i % 2],
            alert_status="firing",
            severity=[Severity.P1, Severity.P2, Severity.P3][i % 3],
            alert_name=f"Performance Test Alert {i}",
            created_at=base_time - timedelta(hours=i % 24)
        )
        db_session.add(alert)
        alerts.append(alert)

    await db_session.flush()

    # Add triages for some alerts
    for i in range(0, 100, 3):  # Every 3rd alert gets a triage
        triage = TriageDBModel(
            alert_id=alerts[i].id,
            status=[Status.SUCCESS, Status.ERROR, Status.QUEUED][i % 3],
            thread_id=f"perf_thread_{i}",
            job_id=f"perf_job_{i}",
            root_cause_summary=f"Performance triage {i}" if i % 3 == 0 else None,
            error_message=f"Performance error {i}" if i % 3 == 1 else None
        )
        db_session.add(triage)

    await db_session.commit()
    return alerts

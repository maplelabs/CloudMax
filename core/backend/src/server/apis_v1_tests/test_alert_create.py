"""
Tests for manual alert creation endpoint.

This test suite verifies:
- Basic alert creation (form mode)
- JSON mode with alternative field names
- DoS protection validators
- Triage triggering logic
- Transaction consistency
- External ID uniqueness
- Database error handling
"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.server.apis_v1 import dependencies
from src.server.web import app

pytestmark = pytest.mark.asyncio


# Helper for DB mock result
def make_mock_result(items):
    """Return a fake SQLAlchemy result where scalars().all() or scalar() works"""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items if isinstance(items, list) else []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = items[0] if items else None
    mock_result.scalar.return_value = items[0] if items else None
    return mock_result


# Fixture for test client
@pytest_asyncio.fixture
async def client(mock_db_session):
    """Async test client with mocked DB session injected into FastAPI app"""
    app.dependency_overrides.clear()
    app.dependency_overrides[dependencies.get_db_session] = lambda: mock_db_session
    app.dependency_overrides[dependencies.get_current_user] = lambda: "test_user@example.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def mock_db_session():
    """Fake async DB session"""
    fake_session = AsyncMock()
    fake_session.flush = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()
    fake_session.add = MagicMock()
    fake_session.execute = AsyncMock(return_value=make_mock_result([]))
    fake_session.scalar = AsyncMock(return_value=None)
    return fake_session


@pytest_asyncio.fixture(autouse=True)
def mock_enqueue_triage():
    """Mock triage job enqueue function"""
    with patch("src.server.apis_v1.alerts.enqueue_triage_job") as mock_enqueue:
        mock_enqueue.return_value = "job_test_123"
        yield mock_enqueue


@pytest_asyncio.fixture(autouse=True)
def mock_config():
    """Mock configuration functions"""
    with patch("src.server.apis_v1.alerts.is_automatic_triage_enabled") as mock_auto_triage, \
         patch("src.server.apis_v1.alerts.is_alert_grouping_enabled") as mock_grouping:
        mock_auto_triage.return_value = True
        mock_grouping.return_value = False  # Direct triage mode for easier testing
        yield mock_auto_triage, mock_grouping


# ==================== BASIC FUNCTIONALITY TESTS ====================

async def test_create_basic_alert_success(client):
    """Test basic alert creation with minimal required fields"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "alert_status": "firing"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Alert created successfully"
    assert data["alert_id"].startswith("manual__")
    assert isinstance(data["triage_triggered"], bool)


async def test_create_alert_with_all_fields(client):
    """Test alert creation with all optional fields"""
    payload = {
        "alert_name": "Production Server Down",
        "severity": "P1",
        "description": "Server is not responding to health checks",
        "alert_status": "firing",
        "labels": {
            "environment": "production",
            "server": "prod-server-01",
            "region": "us-east-1"
        },
        "annotations": {
            "runbook": "https://wiki.company.com/runbooks/server-down",
            "team": "platform"
        },
        "trigger_triage": True
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "manual__" in data["alert_id"]


async def test_create_resolved_alert(client):
    """Test creating an alert with resolved status"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P3",
        "description": "Test description",
        "alert_status": "resolved"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    # Resolved alerts should not trigger triage
    assert data["triage_triggered"] is False


async def test_default_trigger_triage_is_true(client):
    """Test that trigger_triage defaults to True when not specified"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P2",
        "description": "Test description"
        # trigger_triage not specified - should default to True
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    # Since trigger_triage defaults to True and alert is firing, should trigger
    assert response.json()["triage_triggered"] is True


# ==================== VALIDATION TESTS ====================

async def test_missing_required_field_alert_name(client):
    """Test validation error when alert_name is missing"""
    payload = {
        # alert_name missing
        "severity": "P1",
        "description": "Test description"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422  # Validation error


async def test_missing_required_field_severity(client):
    """Test validation error when severity is missing"""
    payload = {
        "alert_name": "Test Alert",
        # severity missing
        "description": "Test description"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422


async def test_missing_required_field_description(client):
    """Test validation error when description is missing"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1"
        # description missing
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422


async def test_invalid_severity_value(client):
    """Test validation error for invalid severity value"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P0",  # Invalid - must be P1, P2, or P3
        "description": "Test description"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422


async def test_invalid_alert_status(client):
    """Test validation error for invalid alert_status"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "alert_status": "pending"  # Invalid - must be "firing" or "resolved"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422


# ==================== DOS PROTECTION TESTS ====================

async def test_dos_protection_alert_name_too_long(client):
    """Test DoS protection: alert_name exceeds 500 characters"""
    payload = {
        "alert_name": "A" * 501,  # 501 characters
        "severity": "P1",
        "description": "Test description"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422
    assert "exceeds maximum length of 500 characters" in response.text


async def test_dos_protection_description_too_long(client):
    """Test DoS protection: description exceeds 500 characters"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "D" * 501  # 501 characters
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422
    assert "exceeds maximum length of 500 characters" in response.text


async def test_dos_protection_too_many_labels(client):
    """Test DoS protection: more than 50 labels"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P3",
        "description": "Test description",
        "labels": {f"key_{i}": "value" for i in range(51)}  # 51 keys
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422
    assert "exceeds maximum of 50 keys" in response.text


async def test_dos_protection_label_key_too_long(client):
    """Test DoS protection: label key exceeds 100 characters"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P3",
        "description": "Test",
        "labels": {"a" * 101: "value"}  # 101 char key
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422
    assert "exceeds maximum length of 100 characters" in response.text


async def test_dos_protection_label_value_too_long(client):
    """Test DoS protection: label value exceeds 500 characters"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P3",
        "description": "Test",
        "labels": {"env": "v" * 501}  # 501 char value
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422
    assert "exceeds maximum length of 500 characters" in response.text


async def test_dos_protection_too_many_annotations(client):
    """Test DoS protection: more than 50 annotations"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P3",
        "description": "Test description",
        "annotations": {f"anno_{i}": "value" for i in range(51)}  # 51 keys
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 422
    assert "exceeds maximum of 50 keys" in response.text


# ==================== TRIAGE TRIGGERING TESTS ====================

async def test_triage_not_triggered_for_resolved_alerts(client):
    """Test that triage is not triggered for resolved alerts"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "alert_status": "resolved",
        "trigger_triage": True  # Explicitly requested
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    # Should not trigger triage for resolved alerts
    assert response.json()["triage_triggered"] is False


async def test_triage_disabled_explicitly(client):
    """Test that triage is not triggered when trigger_triage=False"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "alert_status": "firing",
        "trigger_triage": False  # Explicitly disabled
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    assert response.json()["triage_triggered"] is False


@patch("src.server.apis_v1.alerts.is_automatic_triage_enabled")
async def test_triage_disabled_in_config(mock_auto_triage, client):
    """Test that triage is not triggered when automatic_triage is disabled in config"""
    mock_auto_triage.return_value = False  # Disabled in system config

    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "alert_status": "firing",
        "trigger_triage": True
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    # Should not trigger because automatic_triage is disabled
    assert response.json()["triage_triggered"] is False


# ==================== DATABASE CONSISTENCY TESTS ====================

async def test_alert_created_even_if_triage_fails(client, mock_db_session, mock_enqueue_triage):
    """Test that alert is still created even if triage enqueue fails"""
    # Make triage enqueue fail
    mock_enqueue_triage.side_effect = Exception("Redis connection failed")

    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "trigger_triage": True
    }
    response = await client.post("/v1/alerts", json=payload)

    # Alert should still be created successfully
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["alert_id"].startswith("manual__")
    # Triage should be marked as not triggered
    assert data["triage_triggered"] is False

    # Verify alert was added to database (commit was called)
    assert mock_db_session.add.called
    assert mock_db_session.commit.called


async def test_database_commit_failure_returns_500(client, mock_db_session):
    """Test that database commit failure returns 500 error"""
    # Make the first commit (alert creation) fail
    mock_db_session.commit.side_effect = Exception("Database connection lost")

    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description"
    }
    response = await client.post("/v1/alerts", json=payload)

    # Should return 500 error
    assert response.status_code == 500
    assert "Failed to save alert to database" in response.text

    # Verify rollback was called
    assert mock_db_session.rollback.called


async def test_external_id_uniqueness(client):
    """Test that each alert gets a unique external_id"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description"
    }

    # Create two alerts with identical payloads
    response1 = await client.post("/v1/alerts", json=payload)
    response2 = await client.post("/v1/alerts", json=payload)

    assert response1.status_code == 201
    assert response2.status_code == 201

    id1 = response1.json()["alert_id"]
    id2 = response2.json()["alert_id"]

    # External IDs must be unique (different timestamps/fingerprints)
    assert id1 != id2
    assert id1.startswith("manual__")
    assert id2.startswith("manual__")


async def test_external_id_format(client):
    """Test that external_id follows expected format: manual__{timestamp}__{uuid8}"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    external_id = response.json()["alert_id"]

    # Format: manual__{timestamp}__{uuid8}
    parts = external_id.split("__")
    assert len(parts) == 3
    assert parts[0] == "manual"
    assert parts[1].isdigit()  # Timestamp
    assert len(parts[2]) == 8  # UUID first 8 chars
    assert all(c in "0123456789abcdef-" for c in parts[2])  # Hex characters


# ==================== EDGE CASES ====================

async def test_empty_labels_and_annotations(client):
    """Test that empty labels and annotations are accepted"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "labels": {},
        "annotations": {}
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201


async def test_null_labels_and_annotations(client):
    """Test that null labels and annotations are accepted"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "labels": None,
        "annotations": None
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201


async def test_unicode_in_alert_name(client):
    """Test that Unicode characters are handled properly"""
    payload = {
        "alert_name": "测试警报 🚨 Тест",
        "severity": "P1",
        "description": "Unicode description with émojis 🎉"
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201


async def test_special_characters_in_labels(client):
    """Test that special characters in labels are handled"""
    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test",
        "labels": {
            "env-name": "production-us-east-1",
            "app.kubernetes.io/name": "my-app",
            "team@company.com": "platform"
        }
    }
    response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201


# ==================== CONFIGURATION ERROR HANDLING ====================

@patch("src.server.apis_v1.alerts.is_automatic_triage_enabled")
async def test_config_error_handling_automatic_triage(mock_auto_triage, client):
    """Test that config errors are handled gracefully"""
    # Make config function raise an error
    mock_auto_triage.side_effect = Exception("Database connection failed")

    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "trigger_triage": True
    }
    response = await client.post("/v1/alerts", json=payload)

    # Alert should still be created
    assert response.status_code == 201
    assert response.json()["success"] is True
    # Triage should fail gracefully (default to False on config error)
    assert response.json()["triage_triggered"] is False


@patch("src.server.apis_v1.alerts.is_alert_grouping_enabled")
async def test_config_error_handling_alert_grouping(mock_grouping, client):
    """Test that grouping config errors are handled gracefully"""
    # Make config function raise an error
    mock_grouping.side_effect = Exception("Database connection failed")

    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "trigger_triage": True
    }
    response = await client.post("/v1/alerts", json=payload)

    # Alert should still be created
    assert response.status_code == 201
    assert response.json()["success"] is True


# ==================== TRANSACTION CONSISTENCY TEST ====================

async def test_triage_records_committed_before_job_enqueue(client, mock_db_session, mock_enqueue_triage):
    """
    CRITICAL TEST: Verify triage records are committed to DB BEFORE job is enqueued.

    This prevents the race condition where:
    1. Job is enqueued in Redis
    2. Worker picks up job
    3. Database commit fails
    4. Worker can't find triage records → job fails

    The fix ensures records are committed first, so the job always finds them.
    """
    commit_call_count = 0
    enqueue_called_after_commit = False

    # Track when commit is called
    original_commit = mock_db_session.commit
    async def track_commit():
        nonlocal commit_call_count
        commit_call_count += 1
        await original_commit()

    mock_db_session.commit = track_commit

    # Track when enqueue is called and check if commit happened first
    original_enqueue = mock_enqueue_triage
    def track_enqueue(*args, **kwargs):
        nonlocal enqueue_called_after_commit
        # By the time enqueue is called, at least 2 commits should have happened:
        # 1. Alert creation commit
        # 2. Triage records commit
        enqueue_called_after_commit = (commit_call_count >= 2)
        return original_enqueue(*args, **kwargs)

    with patch("src.server.apis_v1.alerts.enqueue_triage_job", side_effect=track_enqueue):
        payload = {
            "alert_name": "Test Alert",
            "severity": "P1",
            "description": "Test description",
            "trigger_triage": True
        }
        response = await client.post("/v1/alerts", json=payload)

    assert response.status_code == 201
    assert response.json()["triage_triggered"] is True

    # CRITICAL ASSERTION: Triage records must be committed BEFORE enqueue
    assert enqueue_called_after_commit, (
        "RACE CONDITION DETECTED: Job was enqueued before triage records were committed! "
        "This will cause the worker to fail when it tries to load triage records."
    )


async def test_job_enqueue_failure_after_commit_still_succeeds(client, mock_db_session, mock_enqueue_triage):
    """
    Test that if job enqueue fails AFTER triage records are committed,
    the alert and triage records remain in the database.

    This is acceptable behavior because:
    - Alert exists ✓
    - Triage records exist ✓
    - User can manually retry triage later
    """
    # Make enqueue fail
    mock_enqueue_triage.side_effect = Exception("Redis connection failed")

    payload = {
        "alert_name": "Test Alert",
        "severity": "P1",
        "description": "Test description",
        "trigger_triage": True
    }
    response = await client.post("/v1/alerts", json=payload)

    # Alert should still be created successfully
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["alert_id"].startswith("manual__")

    # Triage failed, so it should be marked as not triggered
    assert data["triage_triggered"] is False

    # Verify database commits were called (alert + triage records)
    # The commits succeeded, only the enqueue failed
    assert mock_db_session.commit.call_count >= 1

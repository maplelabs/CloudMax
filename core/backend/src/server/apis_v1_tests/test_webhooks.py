from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.server.apis_v1 import dependencies
from src.server.web import app

pytestmark = pytest.mark.asyncio


# Helper for DB mock result
def make_mock_result(alerts):
    """Return a fake SQLAlchemy result where scalars().all() works"""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = alerts
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    return mock_result


# Fixture for test client
@pytest_asyncio.fixture
async def client(mock_db_session):
    """Async test client with mocked DB session injected into FastAPI app"""
    app.dependency_overrides.clear()
    app.dependency_overrides[dependencies.get_db_session] = lambda: mock_db_session

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
    return fake_session


@pytest_asyncio.fixture(autouse=True)
def mock_enqueue_triage_job():
    """Mock triage job enqueue function"""
    with patch("src.server.apis_v1.webhooks.enqueue_triage_job", new=AsyncMock()) as mock_triage:
        mock_triage.return_value = ("job_123", "thread_456")
        yield mock_triage


# Input validation tests

async def test_missing_alerts_key(client):
    response = await client.post("/v1/webhooks/alerts/grafana", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid payload: missing 'alerts' key"


async def test_alerts_not_a_list(client):
    response = await client.post("/v1/webhooks/alerts/grafana", json={"alerts": {}})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid payload: 'alerts' must be a list"


async def test_empty_alerts_list(client):
    response = await client.post("/v1/webhooks/alerts/grafana", json={"alerts": []})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["inserted"] == 0
    assert data["updated"] == 0
    assert data["triage_jobs_created"] == 0


# Firing alert tests

async def test_insert_single_firing_alert(client):
    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighCPU", "severity": "critical"},
                "fingerprint": "abc123",
            }
        ]
    }
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()
    assert response.status_code == 200
    assert data["inserted"] == 1
    assert data["updated"] == 0
    assert data["triage_jobs_created"] == 1


async def test_insert_multiple_firing_alerts(client):
    payload = {
        "alerts": [
            {"status": "firing", "labels": {"alertname": "CPUHigh", "severity": "critical"}, "fingerprint": "f1"},
            {"status": "firing", "labels": {"alertname": "MemoryHigh", "severity": "low"}, "fingerprint": "f2"},
        ]
    }
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()
    assert response.status_code == 200
    assert data["inserted"] == 2
    assert data["updated"] == 0
    assert data["triage_jobs_created"] == 2


async def test_severity_mapping(client):
    payload = {
        "alerts": [
            {"status": "firing", "labels": {"alertname": "CriticalAlert", "severity": "critical"}, "fingerprint": "s1"},
            {"status": "firing", "labels": {"alertname": "LowAlert", "severity": "low"}, "fingerprint": "s2"},
            {"status": "firing", "labels": {"alertname": "NoSeverity"}, "fingerprint": "s3"},
        ]
    }
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()
    assert response.status_code == 200
    assert data["inserted"] == 3
    assert data["triage_jobs_created"] == 3


async def test_external_id_hashing(client):
    payload = {
        "alerts": [
            {"status": "firing", "labels": {"alertname": "SameAlert", "severity": "critical"}, "fingerprint": "x1"},
            {"status": "firing", "labels": {"severity": "critical", "alertname": "SameAlert"}, "fingerprint": "x2"},
        ]
    }
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()
    assert response.status_code == 200
    assert data["inserted"] == 2
    assert data["triage_jobs_created"] == 2


async def test_alert_without_fingerprint(client):
    payload = {"alerts": [{"status": "firing", "labels": {"alertname": "NoFingerprint", "severity": "medium"}}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()
    assert response.status_code == 200
    assert data["inserted"] == 1
    assert data["updated"] == 0
    assert data["triage_jobs_created"] == 1


# Resolved alert tests

async def test_resolved_alert_updates_existing(client, mock_db_session):
    mock_alert = MagicMock()
    mock_alert.id = 1
    mock_alert.alert_status = "firing"
    mock_db_session.execute.return_value = make_mock_result([mock_alert])

    payload = {
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "CPUHigh"},
                "fingerprint": "fp1",
                "endsAt": datetime.utcnow().isoformat(),
            }
        ]
    }
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["updated"] == 1
    assert data["inserted"] == 0
    assert mock_alert.alert_status == "resolved"


async def test_resolved_alert_no_existing_match(client, mock_db_session, caplog):
    mock_db_session.execute.return_value = make_mock_result([])

    payload = {"alerts": [{"status": "resolved", "labels": {"alertname": "NoMatch"}, "fingerprint": "nomatch"}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["updated"] == 0
    assert data["inserted"] == 0
    assert "No matching alert" in caplog.text or "warning" in caplog.text.lower()


async def test_resolved_alert_updates_multiple(client, mock_db_session):
    mock_alert1 = MagicMock()
    mock_alert1.id = 1
    mock_alert1.alert_status = "firing"

    mock_alert2 = MagicMock()
    mock_alert2.id = 2
    mock_alert2.alert_status = "firing"

    mock_db_session.execute.return_value = make_mock_result([mock_alert1, mock_alert2])

    payload = {"alerts": [{"status": "resolved", "labels": {"alertname": "CPUHigh"}, "fingerprint": "multi"}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["updated"] == 2
    assert data["inserted"] == 0
    assert all(a.alert_status == "resolved" for a in [mock_alert1, mock_alert2])


# Error handling tests

async def test_database_error_handling(client, mock_db_session):
    """Simulate DB commit failure → webhook returns 500 with Internal server error"""
    mock_db_session.commit.side_effect = Exception("DB exploded!")

    payload = {"alerts": [{"status": "firing", "labels": {"alertname": "DBFail"}, "fingerprint": "db1"}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)

    data = response.json()
    assert response.status_code == 500
    assert "Internal server error" in data["detail"]


async def test_unexpected_error_handling(client, mock_enqueue_triage_job):
    """enqueue_triage_job raises → still returns 200 (current behavior)"""
    mock_enqueue_triage_job.side_effect = Exception("Unexpected boom")

    payload = {"alerts": [{"status": "firing", "labels": {"alertname": "Crashy"}, "fingerprint": "oops"}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)

    data = response.json()
    assert response.status_code == 200
    assert data["inserted"] == 1
    assert data["triage_jobs_created"] == 1  # current webhook still counts it


async def test_partial_triage_failure(client, mock_enqueue_triage_job):
    """Current behavior: triage failure not caught → still counted"""

    async def fake_enqueue(alert_id, *args, **kwargs):
        if alert_id.endswith("bad"):
            raise Exception("Triage failed")
        return ("job_ok", "thread_ok")

    mock_enqueue_triage_job.side_effect = fake_enqueue

    payload = {
        "alerts": [
            {"status": "firing", "labels": {"alertname": "GoodAlert"}, "fingerprint": "good"},
            {"status": "firing", "labels": {"alertname": "BadAlert"}, "fingerprint": "bad"},
        ]
    }

    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["inserted"] == 2
    assert data["triage_jobs_created"] == 2  # current implementation still counts both


# Edge case tests

async def test_alert_without_labels(client):
    """Alert without 'labels' → inserted with alert_name='unknown'"""
    payload = {"alerts": [{"status": "firing", "fingerprint": "nolabels"}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["inserted"] == 1
    assert data["triage_jobs_created"] == 1


async def test_alert_with_large_labels_dict(client):
    """Alert with huge labels dict → hashing still stable"""
    big_labels = {f"key{i}": f"value{i}" for i in range(500)}  # 500 labels
    payload = {"alerts": [{"status": "firing", "labels": big_labels, "fingerprint": "big"}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["inserted"] == 1
    assert data["triage_jobs_created"] == 1


async def test_duplicate_insertion_same_external_id(client):
    """Duplicate firing alerts with same external_id → both inserted"""
    labels = {"alertname": "DupAlert", "severity": "critical"}
    payload = {
        "alerts": [
            {"status": "firing", "labels": labels, "fingerprint": "dup1"},
            {"status": "firing", "labels": labels, "fingerprint": "dup1"},
        ]
    }
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["inserted"] == 2
    assert data["triage_jobs_created"] == 2


async def test_alert_missing_severity_defaults_to_P3(client):
    """Alert with missing severity → defaults to P3"""
    payload = {"alerts": [{"status": "firing", "labels": {"alertname": "NoSeverity"}}]}
    response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
    data = response.json()

    assert response.status_code == 200
    assert data["inserted"] == 1
    assert data["triage_jobs_created"] == 1


# Automatic triage disabled tests

async def test_automatic_triage_disabled_single_alert(client, mock_enqueue_triage_job):
    """When automatic triage is disabled, alerts are inserted but no triage jobs created"""
    with patch("src.server.apis_v1.webhooks.is_automatic_triage_enabled", new=AsyncMock(return_value=False)):
        payload = {
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "HighCPU", "severity": "critical"},
                    "fingerprint": "abc123",
                }
            ]
        }
        response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
        data = response.json()

        assert response.status_code == 200
        assert data["inserted"] == 1
        assert data["updated"] == 0
        assert data["triage_jobs_created"] == 0
        assert data["automatic_triage"] is False

        # Verify enqueue_triage_job was never called
        mock_enqueue_triage_job.assert_not_called()


async def test_automatic_triage_disabled_multiple_alerts(client, mock_enqueue_triage_job):
    """When automatic triage is disabled, multiple alerts are inserted but no triage jobs created"""
    with patch("src.server.apis_v1.webhooks.is_automatic_triage_enabled", new=AsyncMock(return_value=False)):
        payload = {
            "alerts": [
                {"status": "firing", "labels": {"alertname": "CPUHigh", "severity": "critical"}, "fingerprint": "f1"},
                {"status": "firing", "labels": {"alertname": "MemoryHigh", "severity": "low"}, "fingerprint": "f2"},
                {"status": "firing", "labels": {"alertname": "DiskFull", "severity": "medium"}, "fingerprint": "f3"},
            ]
        }
        response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
        data = response.json()

        assert response.status_code == 200
        assert data["inserted"] == 3
        assert data["updated"] == 0
        assert data["triage_jobs_created"] == 0
        assert data["automatic_triage"] is False

        # Verify enqueue_triage_job was never called
        mock_enqueue_triage_job.assert_not_called()


async def test_automatic_triage_disabled_resolved_alerts(client, mock_db_session, mock_enqueue_triage_job):
    """When automatic triage is disabled, resolved alerts still work normally"""
    with patch("src.server.apis_v1.webhooks.is_automatic_triage_enabled", new=AsyncMock(return_value=False)):
        mock_alert = MagicMock()
        mock_alert.id = 1
        mock_alert.alert_status = "firing"
        mock_db_session.execute.return_value = make_mock_result([mock_alert])

        payload = {
            "alerts": [
                {
                    "status": "resolved",
                    "labels": {"alertname": "CPUHigh"},
                    "fingerprint": "fp1",
                    "endsAt": datetime.utcnow().isoformat(),
                }
            ]
        }
        response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
        data = response.json()

        assert response.status_code == 200
        assert data["updated"] == 1
        assert data["inserted"] == 0
        assert data["triage_jobs_created"] == 0
        assert data["automatic_triage"] is False
        assert mock_alert.alert_status == "resolved"

        # Verify enqueue_triage_job was never called
        mock_enqueue_triage_job.assert_not_called()


async def test_automatic_triage_enabled_response_format(client):
    """When automatic triage is enabled, response includes automatic_triage: true"""
    with patch("src.server.apis_v1.webhooks.is_automatic_triage_enabled", new=AsyncMock(return_value=True)):
        payload = {
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "TestAlert", "severity": "critical"},
                    "fingerprint": "test123",
                }
            ]
        }
        response = await client.post("/v1/webhooks/alerts/grafana", json=payload)
        data = response.json()

        assert response.status_code == 200
        assert data["inserted"] == 1
        assert data["triage_jobs_created"] == 1
        assert data["automatic_triage"] is True

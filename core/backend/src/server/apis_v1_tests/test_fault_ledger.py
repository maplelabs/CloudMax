"""
Tests for FaultLedger functionality.

Tests cover:
- FaultLedger model creation and relationships
- Alert mapping to FaultLedger
- Evaluation job enqueueing
- Remapping of existing mappings
- POST endpoint for creating FaultLedger entries
- PUT endpoint for updating FaultLedger entries
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.server.apis_v1 import dependencies
from src.server.models.api.enums import FaultLedgerStatus
from src.server.models.db import (
    FaultLedgerDBModel, FaultLedgerToAlertMappingDBModel,
    AlertDBModel, EvaluationDBModel
)
from src.server.web import app

pytestmark = pytest.mark.asyncio


# ---------- Fixtures ----------

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
    fake_session.refresh = AsyncMock()
    fake_session.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: None))
    )
    return fake_session


# ---------- Tests ----------

async def test_fault_ledger_mapping_basic(client, mock_db_session):
    """Test basic FaultLedger mapping with alerts"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

    fake_fault_ledger = MagicMock(
        id=1,
        session_id="test_session_1",
        fault_name="test_fault",
        fault_description="Test fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED
    )

    fake_alert1 = MagicMock(id=101, alert_name="alert1", created_at=start_time + timedelta(minutes=1))
    fake_alert2 = MagicMock(id=102, alert_name="alert2", created_at=start_time + timedelta(minutes=2))

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: [fake_alert1, fake_alert2]))
            elif model is FaultLedgerToAlertMappingDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
            elif model is EvaluationDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    response = await client.put("/v1/fault-ledger/test_session_1", json={})

    assert response.status_code == 200

    # Verify mappings were created
    added_objs = [call[0][0] for call in mock_db_session.add.call_args_list]
    mapping_alert_ids = [obj.alert_id for obj in added_objs if isinstance(obj, FaultLedgerToAlertMappingDBModel)]

    assert set(mapping_alert_ids) == {101, 102}


async def test_fault_ledger_not_found(client, mock_db_session):
    """Test FaultLedger endpoint when ledger doesn't exist"""

    mock_db_session.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(first=lambda: None)
    )

    response = await client.put("/v1/fault-ledger/nonexistent_session", json={})

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_fault_ledger_remapping(client, mock_db_session):
    """Test remapping of alerts from one FaultLedger to another"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

    fake_fault_ledger = MagicMock(
        id=2,
        session_id="test_session_2",
        fault_name="new_fault",
        fault_description="New fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED
    )

    fake_alert = MagicMock(id=201, alert_name="alert1", created_at=start_time + timedelta(minutes=1))

    # Existing mapping
    existing_mapping = MagicMock(
        id=1,
        fault_ledger_id=1,
        alert_id=201
    )

    call_count = [0]

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: [fake_alert]))
            elif model is FaultLedgerToAlertMappingDBModel:
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call returns existing mapping
                    return MagicMock(scalars=lambda: MagicMock(first=lambda: existing_mapping))
                else:
                    return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
            elif model is EvaluationDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    response = await client.put("/v1/fault-ledger/test_session_2", json={})

    assert response.status_code == 200

    # Verify remapping occurred
    assert existing_mapping.fault_ledger_id == 2


async def test_fault_ledger_no_alerts_in_window(client, mock_db_session):
    """Test FaultLedger mapping when no alerts exist in time window"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

    fake_fault_ledger = MagicMock(
        id=3,
        session_id="test_session_3",
        fault_name="no_alerts_fault",
        fault_description="Fault with no alerts",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED
    )

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: []))
            elif model is FaultLedgerToAlertMappingDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    response = await client.put("/v1/fault-ledger/test_session_3", json={})

    assert response.status_code == 200

    # Verify no mappings were created
    added_objs = [call[0][0] for call in mock_db_session.add.call_args_list]
    mapping_objs = [obj for obj in added_objs if isinstance(obj, FaultLedgerToAlertMappingDBModel)]

    assert len(mapping_objs) == 0


async def test_fault_ledger_database_error(client, mock_db_session):
    """Test FaultLedger endpoint when database commit fails"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

    fake_fault_ledger = MagicMock(
        id=4,
        session_id="test_session_4",
        fault_name="error_fault",
        start_time=start_time,
        end_time=end_time
    )

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute
    mock_db_session.commit.side_effect = Exception("Database error")

    response = await client.put("/v1/fault-ledger/test_session_4", json={})

    assert response.status_code == 500
    assert "commit failed" in response.json()["detail"].lower()


# ========== Tests for POST /v1/fault-ledger endpoint ==========

async def test_create_fault_ledger_success(client, mock_db_session):
    """Test successful creation of FaultLedger entry"""

    start_time = datetime.now(timezone.utc)
    configured_duration = 24
    now = datetime.now(timezone.utc)

    # Mock the scalar call for duplicate check
    mock_db_session.scalar = AsyncMock(return_value=None)

    # Mock the add and commit operations
    mock_db_session.add = MagicMock()
    mock_db_session.commit = AsyncMock()

    # Mock refresh to set the id and timestamps
    async def mock_refresh(obj):
        obj.id = 1
        obj.created_at = now
        obj.updated_at = now

    mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

    response = await client.post(
        "/v1/fault-ledger",
        json={
            "fault_name": "probe",
            "fault_description": "probe_testing",
            "start_time": start_time.isoformat(),
            "configured_duration": configured_duration,
            "target_system": "compose-post-service",
            "severity": "low",
            "trigger_mechanism": "manual",
            "session_id": "probe_manual__2025-10-24T04:58:14.858288+00:00"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["fault_name"] == "probe"
    assert data["status"] == "started"  # FaultLedgerStatus.STARTED value


async def test_create_fault_ledger_duplicate_session_id(client, mock_db_session):
    """Test creation fails with duplicate session_id"""

    start_time = datetime.now(timezone.utc)

    # Mock the scalar call to return existing entry
    existing_entry = MagicMock(id=1)
    mock_db_session.scalar = AsyncMock(return_value=existing_entry)

    response = await client.post(
        "/v1/fault-ledger",
        json={
            "fault_name": "probe",
            "fault_description": "probe_testing",
            "start_time": start_time.isoformat(),
            "configured_duration": 24,
            "target_system": "compose-post-service",
            "severity": "low",
            "trigger_mechanism": "manual",
            "session_id": "duplicate_session_id"
        }
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


# ========== Tests for started fault business logic ==========

async def test_create_fault_ledger_reject_within_duration(client, mock_db_session):
    """Test rejecting new fault when started fault is still within duration window"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    configured_duration = 3600  # 1 hour
    now = datetime.now(timezone.utc)

    # Mock existing started fault
    started_fault = MagicMock(
        id=1,
        fault_name="existing_fault",
        start_time=start_time,
        configured_duration=configured_duration,
        status="started"
    )

    # Mock the scalar call to return the started fault
    def fake_scalar(query):
        # First call checks for duplicate session_id (returns None)
        # Second call checks for started fault (returns started_fault)
        if not hasattr(fake_scalar, 'call_count'):
            fake_scalar.call_count = 0
        fake_scalar.call_count += 1

        if fake_scalar.call_count == 1:
            return None  # No duplicate session_id
        else:
            return started_fault  # Found started fault

    mock_db_session.scalar = AsyncMock(side_effect=fake_scalar)

    response = await client.post(
        "/v1/fault-ledger",
        json={
            "fault_name": "new_fault",
            "fault_description": "new fault description",
            "start_time": now.isoformat(),
            "configured_duration": 1800,
            "target_system": "test-system",
            "severity": "high",
            "trigger_mechanism": "manual",
            "session_id": "new_session_reject"
        }
    )

    assert response.status_code == 409
    assert "still within its duration window" in response.json()["detail"]


async def test_create_fault_ledger_mark_expired_and_accept_new(client, mock_db_session):
    """Test marking expired started fault as failed and accepting new fault"""

    start_time = datetime.now(timezone.utc) - timedelta(hours=2)  # 2 hours ago
    configured_duration = 3600  # 1 hour duration
    now = datetime.now(timezone.utc)

    # Mock existing started fault that has expired
    started_fault = MagicMock(
        id=1,
        fault_name="expired_fault",
        start_time=start_time,
        configured_duration=configured_duration,
        status="started"
    )

    # Mock the scalar call
    def fake_scalar(query):
        if not hasattr(fake_scalar, 'call_count'):
            fake_scalar.call_count = 0
        fake_scalar.call_count += 1

        if fake_scalar.call_count == 1:
            return None  # No duplicate session_id
        else:
            return started_fault  # Found started fault

    mock_db_session.scalar = AsyncMock(side_effect=fake_scalar)

    # Mock the add and commit operations
    mock_db_session.add = MagicMock()
    mock_db_session.commit = AsyncMock()

    # Mock refresh to set the id and timestamps
    async def mock_refresh(obj):
        obj.id = 2
        obj.created_at = now
        obj.updated_at = now

    mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

    response = await client.post(
        "/v1/fault-ledger",
        json={
            "fault_name": "new_fault_after_expiry",
            "fault_description": "new fault after expiry",
            "start_time": now.isoformat(),
            "configured_duration": 1800,
            "target_system": "test-system",
            "severity": "high",
            "trigger_mechanism": "manual",
            "session_id": "new_session_accept"
        }
    )

    assert response.status_code == 201
    # Verify the old fault was marked as failed
    assert started_fault.status == "failed"


# ========== Tests for get_chaos_max_workflow_time_minutes_from_fault_ledger ==========

async def test_get_max_workflow_time_from_fault_ledger_success(mock_db_session):
    """Test getting max workflow time from FaultLedger's configured_duration"""
    from src.server.apis_v1.config import get_chaos_max_workflow_time_minutes_from_fault_ledger

    # Mock the execute call to return configured_duration in seconds (e.g., 1440 seconds = 24 minutes)
    configured_duration_seconds = 1440  # 24 minutes

    def fake_execute(query):
        return MagicMock(scalar=lambda: configured_duration_seconds)

    mock_db_session.execute = AsyncMock(side_effect=fake_execute)

    result = await get_chaos_max_workflow_time_minutes_from_fault_ledger(
        fault_ledger_id=1,
        db=mock_db_session
    )

    # Should convert 1440 seconds to 24 minutes
    assert result == 24


async def test_get_max_workflow_time_from_fault_ledger_not_found(mock_db_session):
    """Test fallback to .env when FaultLedger not found"""
    from src.server.apis_v1.config import get_chaos_max_workflow_time_minutes_from_fault_ledger
    from unittest.mock import patch

    # Mock the execute call to return None (FaultLedger not found)
    def fake_execute(query):
        return MagicMock(scalar=lambda: None)

    mock_db_session.execute = AsyncMock(side_effect=fake_execute)

    # Mock the .env value
    with patch('os.getenv', return_value='30'):
        result = await get_chaos_max_workflow_time_minutes_from_fault_ledger(
            fault_ledger_id=999,
            db=mock_db_session
        )

    # Should fall back to .env value (default 30)
    assert result == 30


async def test_get_max_workflow_time_from_fault_ledger_error(mock_db_session):
    """Test fallback to .env when database error occurs"""
    from src.server.apis_v1.config import get_chaos_max_workflow_time_minutes_from_fault_ledger
    from unittest.mock import patch

    # Mock the execute call to raise an exception
    mock_db_session.execute = AsyncMock(side_effect=Exception("Database error"))

    # Mock the .env value
    with patch('os.getenv', return_value='30'):
        result = await get_chaos_max_workflow_time_minutes_from_fault_ledger(
            fault_ledger_id=1,
            db=mock_db_session
        )

    # Should fall back to .env value (default 30)
    assert result == 30


# ========== Tests for alert_names filtering ==========

async def test_fault_ledger_mapping_with_alert_names_filter(client, mock_db_session):
    """Test FaultLedger mapping with end_time and status update"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)
    new_end_time = datetime.now(timezone.utc) + timedelta(minutes=5)

    fake_fault_ledger = MagicMock(
        id=1,
        session_id="test_session_update_1",
        fault_name="test_fault",
        fault_description="Test fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED,
        alert_names=["alert1", "alert2"]  # Pre-existing alert names
    )

    # Create alerts with different names
    fake_alert1 = MagicMock(id=101, alert_name="alert1", created_at=start_time + timedelta(minutes=1))
    fake_alert2 = MagicMock(id=102, alert_name="alert2", created_at=start_time + timedelta(minutes=2))

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                # Return alerts that match the pre-existing alert_names filter
                return MagicMock(scalars=lambda: MagicMock(all=lambda: [fake_alert1, fake_alert2]))
            elif model is FaultLedgerToAlertMappingDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
            elif model is EvaluationDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    # Send PUT request with end_time and status
    response = await client.put(
        "/v1/fault-ledger/test_session_update_1",
        json={"end_time": new_end_time.isoformat(), "status": "completed"}
    )

    assert response.status_code == 200

    # Verify end_time and status were updated
    assert fake_fault_ledger.end_time == new_end_time
    assert fake_fault_ledger.status == "completed"

    # Verify alerts were mapped based on pre-existing alert_names
    added_objs = [call[0][0] for call in mock_db_session.add.call_args_list]
    mapping_alert_ids = [obj.alert_id for obj in added_objs if isinstance(obj, FaultLedgerToAlertMappingDBModel)]

    assert set(mapping_alert_ids) == {101, 102}


async def test_fault_ledger_mapping_without_alert_names_filter(client, mock_db_session):
    """Test FaultLedger mapping without alert_names (all alerts in time window)"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

    fake_fault_ledger = MagicMock(
        id=1,
        session_id="test_session_update_2",
        fault_name="test_fault",
        fault_description="Test fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED,
        alert_names=None  # No alert_names filter
    )

    fake_alert1 = MagicMock(id=101, alert_name="alert1", created_at=start_time + timedelta(minutes=1))
    fake_alert2 = MagicMock(id=102, alert_name="alert2", created_at=start_time + timedelta(minutes=2))
    fake_alert3 = MagicMock(id=103, alert_name="alert3", created_at=start_time + timedelta(minutes=3))

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                # Return all alerts when no alert_names filter is applied
                return MagicMock(scalars=lambda: MagicMock(all=lambda: [fake_alert1, fake_alert2, fake_alert3]))
            elif model is FaultLedgerToAlertMappingDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
            elif model is EvaluationDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: None))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    # Send PUT request with only end_time (no alert_names parameter)
    response = await client.put(
        "/v1/fault-ledger/test_session_update_2",
        json={"end_time": end_time.isoformat()}
    )

    assert response.status_code == 200

    # Verify alert_names was not modified (remains None)
    assert fake_fault_ledger.alert_names is None

    # Verify all alerts were mapped
    added_objs = [call[0][0] for call in mock_db_session.add.call_args_list]
    mapping_alert_ids = [obj.alert_id for obj in added_objs if isinstance(obj, FaultLedgerToAlertMappingDBModel)]

    assert set(mapping_alert_ids) == {101, 102, 103}


# ========== Tests for end_time and status updates ==========

async def test_fault_ledger_update_end_time(client, mock_db_session):
    """Test updating end_time via PUT endpoint"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)
    new_end_time = datetime.now(timezone.utc) + timedelta(minutes=5)

    fake_fault_ledger = MagicMock(
        id=1,
        session_id="test_session_end_time",
        fault_name="test_fault",
        fault_description="Test fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED,
        alert_names=None
    )

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    # Send PUT request with new end_time
    response = await client.put(
        "/v1/fault-ledger/test_session_end_time",
        json={"end_time": new_end_time.isoformat()}
    )

    assert response.status_code == 200
    # Verify end_time was updated
    assert fake_fault_ledger.end_time == new_end_time


async def test_fault_ledger_update_status(client, mock_db_session):
    """Test updating status via PUT endpoint"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)

    fake_fault_ledger = MagicMock(
        id=1,
        session_id="test_session_status",
        fault_name="test_fault",
        fault_description="Test fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED,
        alert_names=None
    )

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    # Send PUT request with new status
    response = await client.put(
        "/v1/fault-ledger/test_session_status",
        json={"status": "completed"}
    )

    assert response.status_code == 200
    # Verify status was updated
    assert fake_fault_ledger.status == FaultLedgerStatus.COMPLETED


async def test_fault_ledger_update_end_time_and_status(client, mock_db_session):
    """Test updating both end_time and status via PUT endpoint"""

    start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    end_time = datetime.now(timezone.utc)
    new_end_time = datetime.now(timezone.utc) + timedelta(minutes=5)

    fake_fault_ledger = MagicMock(
        id=1,
        session_id="test_session_both",
        fault_name="test_fault",
        fault_description="Test fault description",
        start_time=start_time,
        end_time=end_time,
        status=FaultLedgerStatus.STARTED,
        alert_names=None
    )

    def fake_execute(query):
        if hasattr(query, "column_descriptions"):
            model = query.column_descriptions[0].get("entity")
            if model is FaultLedgerDBModel:
                return MagicMock(scalars=lambda: MagicMock(first=lambda: fake_fault_ledger))
            elif model is AlertDBModel:
                return MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        return MagicMock()

    mock_db_session.execute.side_effect = fake_execute

    # Send PUT request with both end_time and status
    response = await client.put(
        "/v1/fault-ledger/test_session_both",
        json={
            "end_time": new_end_time.isoformat(),
            "status": "failed"
        }
    )

    assert response.status_code == 200
    # Verify both were updated
    assert fake_fault_ledger.end_time == new_end_time
    assert fake_fault_ledger.status == FaultLedgerStatus.FAILED

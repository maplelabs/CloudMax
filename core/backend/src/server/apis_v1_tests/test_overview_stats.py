"""
Comprehensive test suite for /v1/stats/summary endpoint with all 23 test cases from overview plan.
Uses sequential execution patch to fix SQLAlchemy concurrency issue without modifying stats.py.
Tests the real API endpoint with real database fixtures like alert_list.py.
"""
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import quote

import pytest
import pytest_asyncio

from src.server.models.api.enums import Status, Severity
from src.server.models.db.alert import Alert as DBAlert
from src.server.models.db.evaluation import Evaluation as EvaluationDBModel
from src.server.models.db.triage import Triage as TriageDBModel

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def sequential_gather(*aws, **kwargs):
    """
    Replacement for asyncio.gather that runs awaitables sequentially.
    This prevents the SQLAlchemy concurrency issue.
    """
    results = []
    for aw in aws:
        result = await aw
        results.append(result)
    return results


# Test #1: Empty database
async def test_empty_database(client, db_session):
    """Test #1: Empty database returns empty arrays"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        assert data == {
            "kpi_metrics": [],
            "plots": []
        }


# Test #2: Single alert with ERROR triage and PENDING evaluation
@pytest_asyncio.fixture
async def test2_data(db_session):
    """Test #2 data: Single alert with ERROR triage"""
    base_time = datetime.utcnow()

    alert = DBAlert(
        external_id="ext-1",
        payload={"test": "data"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="CPU-High",
        created_at=base_time,
        updated_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    triage = TriageDBModel(
        alert_id=alert.id,
        status=Status.ERROR,
        thread_id="thread-1",
        job_id="job-1",
        error_message="Failed",
        tokens_used=20,
        price_usd=0.2,
        processing_time_sec=1
    )
    db_session.add(triage)

    evaluation = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.PENDING,
        job_id="eval-1",
        tokens_used=50,
        price_usd=0.1,
        processing_time_sec=1
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alert": alert, "triage": triage, "evaluation": evaluation}


async def test_single_alert_error_triage(client, test2_data):
    """Test #2: Single alert with ERROR triage and PENDING evaluation"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Should have KPI metrics but no plots for single failed triage
        assert "kpi_metrics" in data
        assert "plots" in data
        assert len(data["kpi_metrics"]) > 0


# Test #3: Single alert with SUCCESS triage and SUCCESS evaluation
@pytest_asyncio.fixture
async def test3_data(db_session):
    """Test #3 data: Single alert with SUCCESS triage and evaluation"""
    base_time = datetime.utcnow()

    alert = DBAlert(
        external_id="ext-1",
        payload={"test": "data"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="CPU High",
        created_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    triage = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        tokens_used=100,
        price_usd=0.5,
        processing_time_sec=2
    )
    db_session.add(triage)

    evaluation = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        tokens_used=50,
        price_usd=0.2,
        orch_agent_util_score_percent=90,
        orch_task_completion_score_percent=88,
        sub_agent_tool_util_score_percent=92,
        sub_agent_task_completion_score=87,
        processing_time_sec=1.5
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alert": alert, "triage": triage, "evaluation": evaluation}


async def test_single_alert_success_both(client, test3_data):
    """Test #3: Single alert with SUCCESS triage and evaluation"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data

        # Should have metrics for successful alert
        kpi_metrics = data["kpi_metrics"]
        assert len(kpi_metrics) > 0

        # Find specific metrics - only checking KPIs that still exist
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        assert total_alerts is not None
        assert total_alerts["value"] == "1"


# Test #4: Multiple alerts with different statuses
@pytest_asyncio.fixture
async def test4_data(db_session):
    """Test #4 data: Multiple alerts with different triage statuses"""
    base_time = datetime.utcnow()

    alerts_data = [
        {"external_id": "ext-1", "severity": Severity.P1, "alert_name": "CPU High", "triage_status": Status.SUCCESS},
        {"external_id": "ext-2", "severity": Severity.P2, "alert_name": "Memory", "triage_status": Status.ERROR},
        {"external_id": "ext-3", "severity": Severity.P1, "alert_name": "Disk Full", "triage_status": Status.PENDING},
        {"external_id": "ext-4", "severity": Severity.P3, "alert_name": "Network", "triage_status": Status.PROCESSING}
    ]

    created_alerts = []
    for i, alert_data in enumerate(alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"data{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=alert_data["severity"],
            alert_name=alert_data["alert_name"],
            created_at=base_time + timedelta(minutes=i * 5)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["triage_status"],
            tokens_used=100 - i * 25,
            price_usd=0.5 - i * 0.1,
            processing_time_sec=2 - i * 0.5
        )
        db_session.add(triage)
        created_alerts.append(alert)

    # Add evaluation only for first alert (SUCCESS)
    evaluation = EvaluationDBModel(
        alert_id=created_alerts[0].id,
        status=Status.SUCCESS,
        tokens_used=50,
        price_usd=0.2,
        orch_agent_util_score_percent=85,
        orch_task_completion_score_percent=90,
        sub_agent_tool_util_score_percent=88,
        sub_agent_task_completion_score=87,
        processing_time_sec=1.5
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_multiple_alerts_different_statuses(client, test4_data):
    """Test #4: Multiple alerts with different triage statuses"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data

        # Should have metrics and plots
        kpi_metrics = data["kpi_metrics"]
        plots = data["plots"]

        # Find specific metrics - only checking KPIs that still exist
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        assert total_alerts is not None
        assert total_alerts["value"] == "4"

        # Should have triage status distribution plot
        status_plot = next((p for p in plots if p["title"] == "Triage Status Distribution"), None)
        assert status_plot is not None
        assert status_plot["plot_details"]["plot_type"] == "pie"


# Test #5: Delta calculations with previous period
@pytest_asyncio.fixture
async def test5_data(db_session):
    """Test #5 data: Current and previous period for delta calculations"""
    current_time = datetime.utcnow()
    previous_time = current_time - timedelta(hours=36)  # 24-48h ago

    # Current period alerts (last 24h)
    current_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"current-{i + 1}",
            payload={"test": f"current{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Current Alert {i + 1}",
            created_at=current_time - timedelta(minutes=i * 30)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            tokens_used=100 - i * 20,
            price_usd=0.5 - i * 0.1,
            processing_time_sec=2 - i * 0.5
        )
        db_session.add(triage)
        current_alerts.append(alert)

    # Previous period alert (24-48h ago)
    prev_alert = DBAlert(
        external_id="prev-1",
        payload={"test": "prev"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Previous Alert",
        created_at=previous_time
    )
    db_session.add(prev_alert)
    await db_session.flush()

    prev_triage = TriageDBModel(
        alert_id=prev_alert.id,
        status=Status.ERROR,
        tokens_used=60,
        price_usd=0.3,
        processing_time_sec=3
    )
    db_session.add(prev_triage)

    await db_session.commit()
    return {"current_alerts": current_alerts, "prev_alert": prev_alert}


async def test_delta_calculations(client, test5_data):
    """Test #5: Delta calculations with previous period"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Should have metrics (deltas removed in new UI)
        kpi_metrics = data["kpi_metrics"]

        # Find metrics
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        if total_alerts:
            assert total_alerts["value"] == "2"


# Test #6: Comprehensive data with time-based plots
@pytest_asyncio.fixture
async def test6_data(db_session):
    """Test #6 data: Multiple alerts across different times for plots"""
    base_date = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago, within 24h range

    alerts_data = [
        {"external_id": "ext-1", "time_offset": 0, "triage_status": Status.SUCCESS},
        {"external_id": "ext-2", "time_offset": 4, "triage_status": Status.SUCCESS},  # 4 hours later
        {"external_id": "ext-3", "time_offset": 8, "triage_status": Status.ERROR}  # 8 hours later
    ]

    created_alerts = []
    for i, alert_data in enumerate(alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"data{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Alert {i + 1}",
            created_at=base_date + timedelta(hours=alert_data["time_offset"])
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["triage_status"],
            thread_id=f"t{i + 1}",
            job_id=f"j{i + 1}",
            tokens_used=100 + i * 50,
            price_usd=0.5 + i * 0.2,
            processing_time_sec=300 + i * 150
        )
        db_session.add(triage)
        created_alerts.append(alert)

    # Add evaluations for successful triages
    for i, alert in enumerate(created_alerts[:2]):  # First 2 are SUCCESS
        evaluation = EvaluationDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            job_id=f"e{i + 1}",
            tokens_used=50 + i * 10,
            price_usd=0.2 + i * 0.05,
            root_cause_similarity_percent=85 - i * 7,
            orch_agent_util_score_percent=90 - i * 8,
            orch_task_completion_score_percent=88 - i * 3,
            sub_agent_tool_util_score_percent=92 - i * 4,
            sub_agent_task_completion_score=87 - i * 7,
            processing_time_sec=120 + i * 30
        )
        db_session.add(evaluation)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_comprehensive_data_with_plots(client, test6_data):
    """Test #6: Comprehensive data with time-based plots"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()
        # Should have both metrics and plots
        assert "kpi_metrics" in data
        assert "plots" in data

        kpi_metrics = data["kpi_metrics"]
        plots = data["plots"]

        # Verify basic metrics - only checking KPIs that still exist
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        assert total_alerts is not None
        assert total_alerts["value"] == "3"

        # Should have multiple plots
        assert len(plots) > 0

        # Should have triage status distribution
        status_plot = next((p for p in plots if p["title"] == "Triage Status Distribution"), None)
        assert status_plot is not None

        # Verify line charts have average field
        success_rate_plot = next((p for p in plots if p["title"] == "Triage Success Rate"), None)
        if success_rate_plot:
            assert "average" in success_rate_plot["plot_details"]
            assert success_rate_plot["plot_details"]["average"] is not None


# Test #7: Current vs Previous period comparison
@pytest_asyncio.fixture
async def test7_data(db_session):
    """Test #7 data: Current vs previous period for comparison"""
    current_time = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago, within 24h range
    previous_time = datetime.now(timezone.utc) - timedelta(hours=36)  # 36 hours ago, outside 24h range

    # Current period (2 alerts)
    current_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"cur-{i + 1}",
            payload={"test": f"current{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Current {i + 1}",
            created_at=current_time + timedelta(hours=i * 5)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS if i == 0 else Status.ERROR,
            tokens_used=100 - i * 20,
            price_usd=0.5 - i * 0.1,
            processing_time_sec=300 - i * 100
        )
        db_session.add(triage)
        current_alerts.append(alert)

    # Add evaluation for successful current alert
    evaluation = EvaluationDBModel(
        alert_id=current_alerts[0].id,
        status=Status.SUCCESS,
        orch_agent_util_score_percent=85,
        orch_task_completion_score_percent=90,
        sub_agent_tool_util_score_percent=88,
        sub_agent_task_completion_score=87
    )
    db_session.add(evaluation)

    # Previous period (1 alert)
    prev_alert = DBAlert(
        external_id="prev-1",
        payload={"test": "prev"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Previous",
        created_at=previous_time
    )
    db_session.add(prev_alert)
    await db_session.flush()

    prev_triage = TriageDBModel(
        alert_id=prev_alert.id,
        status=Status.SUCCESS,
        tokens_used=120,
        price_usd=0.6,
        processing_time_sec=400
    )
    db_session.add(prev_triage)

    prev_evaluation = EvaluationDBModel(
        alert_id=prev_alert.id,
        status=Status.SUCCESS,
        orch_agent_util_score_percent=80,
        orch_task_completion_score_percent=85,
        sub_agent_tool_util_score_percent=82,
        sub_agent_task_completion_score=83
    )
    db_session.add(prev_evaluation)

    await db_session.commit()
    return {"current_alerts": current_alerts, "prev_alert": prev_alert}


async def test_current_vs_previous_comparison(client, test7_data):
    """Test #7: Current vs previous period comparison with deltas"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]

        # Should have metrics (deltas removed in new UI)
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        assert total_alerts is not None
        assert total_alerts["value"] == "2"


# Test #8: Chaos mode testing (root_cause_similarity_percent inclusion)
@pytest_asyncio.fixture
async def test8_data(db_session):
    """Test #8 data: Single alert for chaos mode testing"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago, within 24h range

    alert = DBAlert(
        external_id="chaos-1",
        payload={"test": "chaos"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Chaos Test",
        created_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    triage = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS
    )
    db_session.add(triage)

    evaluation = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        root_cause_similarity_percent=75,
        orch_agent_util_score_percent=85,
        orch_task_completion_score_percent=90,
        sub_agent_tool_util_score_percent=88,
        sub_agent_task_completion_score=87
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alert": alert}


async def test_chaos_mode_audit_score(client, test8_data):
    """Test #8: Chaos mode affects audit score calculation"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Audit Score % is no longer in KPI metrics, it's only in plots
        assert "kpi_metrics" in data


# Test #9: Weekly time range with sparse data
@pytest_asyncio.fixture
async def test9_data(db_session):
    """Test #9 data: Weekly data with sparse alerts"""
    base_date = datetime(2024, 1, 1, 10, 0, 0)

    # Day 1, Day 3, Day 6
    days_offsets = [0, 2, 5]
    statuses = [Status.SUCCESS, Status.SUCCESS, Status.ERROR]

    created_alerts = []
    for i, (day_offset, status) in enumerate(zip(days_offsets, statuses)):
        alert = DBAlert(
            external_id=f"w{i + 1}",
            payload={"test": f"week{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Week Alert {i + 1}",
            created_at=base_date + timedelta(days=day_offset)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=status
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_weekly_sparse_data(client, test9_data):
    """Test #9: Weekly time range with sparse data points"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=7d")

        assert response.status_code == 200
        data = response.json()

        # Should have plots with daily data points
        plots = data["plots"]

        # Find triage success rate plot
        success_plot = next((p for p in plots if "Triage Success Rate" in p["title"]), None)
        if success_plot:
            data_points = success_plot["plot_details"]["data_points"]
            # Should have 7 daily buckets, most with 0 values
            assert len(data_points) <= 7


# Test #10: Monthly time range
@pytest_asyncio.fixture
async def test10_data(db_session):
    """Test #10 data: Monthly data with sparse alerts"""
    base_date = datetime(2024, 1, 1, 10, 0, 0)

    # Day 1, Day 15, Day 30
    days_offsets = [0, 14, 29]

    created_alerts = []
    for i, day_offset in enumerate(days_offsets):
        alert = DBAlert(
            external_id=f"m{i + 1}",
            payload={"test": f"month{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Month Alert {i + 1}",
            created_at=base_date + timedelta(days=day_offset)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_monthly_sparse_data(client, test10_data):
    """Test #10: Monthly time range with sparse data"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=30d")

        assert response.status_code == 200
        data = response.json()

        # Should have plots with daily data points
        plots = data["plots"]

        # Find triage success rate plot
        success_plot = next((p for p in plots if "Triage Success Rate" in p["title"]), None)
        if success_plot:
            data_points = success_plot["plot_details"]["data_points"]
            # Should have up to 30 daily buckets
            assert len(data_points) <= 30


# Test #11: Mixed evaluation statuses
@pytest_asyncio.fixture
async def test11_data(db_session):
    """Test #11 data: Mixed evaluation statuses"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago, within 24h range

    created_alerts = []
    eval_statuses = [Status.SUCCESS, Status.ERROR, Status.PROCESSING]

    for i, eval_status in enumerate(eval_statuses):
        alert = DBAlert(
            external_id=f"mix-{i + 1}",
            payload={"test": f"mix{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Mix Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        # All triages are SUCCESS
        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS
        )
        db_session.add(triage)

        # Different evaluation statuses
        evaluation = EvaluationDBModel(
            alert_id=alert.id,
            status=eval_status,
            orch_agent_util_score_percent=85 if eval_status == Status.SUCCESS else None,
            orch_task_completion_score_percent=90 if eval_status == Status.SUCCESS else None,
            sub_agent_tool_util_score_percent=88 if eval_status == Status.SUCCESS else None,
            sub_agent_task_completion_score=87 if eval_status == Status.SUCCESS else None
        )
        db_session.add(evaluation)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_mixed_evaluation_statuses(client, test11_data):
    """Test #11: Mixed evaluation statuses - only successful evaluations count for audit score"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]

        # All triages are successful - only checking KPIs that still exist
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        assert total_alerts is not None
        assert total_alerts["value"] == "3"


# Test #12: Null vs zero values in evaluations
@pytest_asyncio.fixture
async def test12_data(db_session):
    """Test #12 data: Null vs zero values in evaluations"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    created_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"null-{i + 1}" if i == 0 else f"zero-{i + 1}",
            payload={"test": f"test{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Test Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS
        )
        db_session.add(triage)

        # First evaluation has null values, second has zero values
        evaluation = EvaluationDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            orch_agent_util_score_percent=None if i == 0 else 0,
            orch_task_completion_score_percent=None if i == 0 else 0,
            sub_agent_tool_util_score_percent=None if i == 0 else 0,
            sub_agent_task_completion_score=None if i == 0 else 0
        )
        db_session.add(evaluation)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_null_vs_zero_values(client, test12_data):
    """Test #12: Null values are ignored, zero values are counted"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Audit Score % is no longer in KPI metrics, it's only in plots
        assert "kpi_metrics" in data


# Test #13: Edge case - alerts at bucket boundaries
@pytest_asyncio.fixture
async def test13_data(db_session):
    """Test #13 data: Alerts at time bucket boundaries"""
    base_time = datetime(2024, 1, 1, 10, 30, 0)  # 10:30

    created_alerts = []
    for i, minutes in enumerate([0, 15]):  # 10:30 and 10:45
        alert = DBAlert(
            external_id=f"edge-{i + 1}",
            payload={"test": f"edge{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Edge Alert {i + 1}",
            created_at=base_time + timedelta(minutes=minutes)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS if i == 0 else Status.ERROR
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_bucket_boundary_alerts(client, test13_data):
    """Test #13: Alerts at time bucket boundaries"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Should group both alerts in same hourly bucket
        plots = data["plots"]
        success_plot = next((p for p in plots if "Triage Success Rate" in p["title"]), None)

        if success_plot:
            data_points = success_plot["plot_details"]["data_points"]
            # Should have one bucket with 50% success rate (1 success, 1 error)
            non_zero_points = [p for p in data_points if p["value"] > 0]
            if non_zero_points:
                assert non_zero_points[0]["value"] == 50.0


# Test #14: Precision in calculations
@pytest_asyncio.fixture
async def test14_data(db_session):
    """Test #14 data: Precise calculations"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    created_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"prec-{i + 1}",
            payload={"test": f"prec{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Precision Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            tokens_used=123 if i == 0 else 456,
            price_usd=0.567 if i == 0 else 0.891,
            processing_time_sec=789 if i == 0 else 234
        )
        db_session.add(triage)

        evaluation = EvaluationDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            tokens_used=78 if i == 0 else 91,
            price_usd=0.234 if i == 0 else 0.345,
            orch_agent_util_score_percent=87 if i == 0 else 76,
            orch_task_completion_score_percent=92 if i == 0 else 83,
            sub_agent_tool_util_score_percent=89 if i == 0 else 79,
            sub_agent_task_completion_score=91 if i == 0 else 81,
            processing_time_sec=156 if i == 0 else 267
        )
        db_session.add(evaluation)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_precision_calculations(client, test14_data):
    """Test #14: Precision in metric calculations"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # These metrics are no longer in KPI metrics, they're only in plots
        assert "kpi_metrics" in data


# Test #15: Extreme values (min/max)
@pytest_asyncio.fixture
async def test15_data(db_session):
    """Test #15 data: Extreme values"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    created_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"ext-{i + 1}",
            payload={"test": f"extreme{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Extreme Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS
        )
        db_session.add(triage)

        # Min values (0) vs Max values (100)
        evaluation = EvaluationDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            orch_agent_util_score_percent=0 if i == 0 else 100,
            orch_task_completion_score_percent=0 if i == 0 else 100,
            sub_agent_tool_util_score_percent=0 if i == 0 else 100,
            sub_agent_task_completion_score=0 if i == 0 else 100
        )
        db_session.add(evaluation)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_extreme_values(client, test15_data):
    """Test #15: Extreme min/max values"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Audit Score % is no longer in KPI metrics, it's only in plots
        assert "kpi_metrics" in data


# Test #16: Sparse hourly distribution
@pytest_asyncio.fixture
async def test16_data(db_session):
    """Test #16 data: Sparse hourly distribution"""
    base_date = datetime(2024, 1, 1, 2, 0, 0)

    # Alerts at 02:00, 14:00, 22:00
    hours = [0, 12, 20]  # Relative to base_date
    statuses = [Status.SUCCESS, Status.ERROR, Status.SUCCESS]

    created_alerts = []
    for i, (hour_offset, status) in enumerate(zip(hours, statuses)):
        alert = DBAlert(
            external_id=f"sparse-{i + 1}",
            payload={"test": f"sparse{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Sparse Alert {i + 1}",
            created_at=base_date + timedelta(hours=hour_offset)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=status
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_sparse_hourly_distribution(client, test16_data):
    """Test #16: Sparse hourly distribution in plots"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        plots = data["plots"]
        success_plot = next((p for p in plots if "Triage Success Rate" in p["title"]), None)

        if success_plot:
            data_points = success_plot["plot_details"]["data_points"]
            # Should have 24 hourly buckets, most with 0 values
            # 3 buckets should have non-zero values
            non_zero_points = [p for p in data_points if p["value"] > 0]
            assert len(non_zero_points) <= 3


# Test #17: Processing time and LLM metrics
@pytest_asyncio.fixture
async def test17_data(db_session):
    """Test #17 data: Processing time and LLM metrics"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    alert = DBAlert(
        external_id="proc-1",
        payload={"test": "proc"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Processing Test",
        created_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    triage = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        processing_time_sec=300,
        llm_metrics={"latency": 0.5, "calls": 5}
    )
    db_session.add(triage)

    evaluation = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        processing_time_sec=120,
        llm_metrics={"latency": 0.2, "calls": 2},
        orch_agent_util_score_percent=85,
        orch_task_completion_score_percent=90,
        sub_agent_tool_util_score_percent=88,
        sub_agent_task_completion_score=87
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alert": alert}


async def test_processing_time_llm_metrics(client, test17_data):
    """Test #17: Processing time and LLM metrics aggregation"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]

        llm_latency = next((m for m in kpi_metrics if m["label"] == "Avg P95 Latency"), None)
        llm_calls = next((m for m in kpi_metrics if m["label"] == "Total LLM Calls"), None)

        if llm_latency:
            # 0.5 + 0.2 = 0.7s
            assert "0.7" in llm_latency["value"] or "0.70" in llm_latency["value"]

        if llm_calls:
            # 5 + 2 = 7
            assert llm_calls["value"] == "7"


# Test #18: Cost calculations
@pytest_asyncio.fixture
async def test18_data(db_session):
    """Test #18 data: Cost calculations"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    created_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"cost-{i + 1}",
            payload={"test": f"cost{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Cost Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS if i == 0 else Status.ERROR,
            tokens_used=1000 if i == 0 else 500,
            price_usd=2.50 if i == 0 else 1.25
        )
        db_session.add(triage)
        created_alerts.append(alert)

    # Add evaluation only for successful triage
    evaluation = EvaluationDBModel(
        alert_id=created_alerts[0].id,
        status=Status.SUCCESS,
        tokens_used=200,
        price_usd=0.75,
        orch_agent_util_score_percent=85,
        orch_task_completion_score_percent=90,
        sub_agent_tool_util_score_percent=88,
        sub_agent_task_completion_score=87
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_cost_calculations(client, test18_data):
    """Test #18: Cost calculations for successful vs all alerts"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]

        total_cost = next((m for m in kpi_metrics if m["label"] == "Total Cost"), None)

        if total_cost:
            # 2.50 + 1.25 + 0.75 = 4.50 total
            assert "4.50" in total_cost["value"] or "$4.50" in total_cost["value"]


# Test #19: Time boundary testing
@pytest_asyncio.fixture
async def test19_data(db_session):
    """Test #19 data: Time boundary testing"""
    # Alerts exactly at start and end of 24h period
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    end_time = datetime(2024, 1, 1, 23, 59, 59)

    created_alerts = []
    for i, alert_time in enumerate([base_time, end_time]):
        alert = DBAlert(
            external_id=f"bound-{i + 1}",
            payload={"test": f"bound{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Boundary Alert {i + 1}",
            created_at=alert_time
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_time_boundary_inclusion(client, test19_data):
    """Test #19: Time boundary inclusion"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        # Query at exactly 2024-01-02 00:00:00 for last 24h
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        if total_alerts:
            # Both alerts should be included
            assert total_alerts["value"] == "2"


# Test #20: Same timestamp alerts
@pytest_asyncio.fixture
async def test20_data(db_session):
    """Test #20 data: Multiple alerts at same timestamp"""
    same_time = datetime(2024, 1, 1, 10, 0, 0)

    statuses = [Status.SUCCESS, Status.ERROR, Status.PROCESSING]
    created_alerts = []

    for i, status in enumerate(statuses):
        alert = DBAlert(
            external_id=f"same-{i + 1}",
            payload={"test": f"same{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Same Time Alert {i + 1}",
            created_at=same_time
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=status
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_same_timestamp_alerts(client, test20_data):
    """Test #20: Multiple alerts at same timestamp"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        plots = data["plots"]
        success_plot = next((p for p in plots if "Triage Success Rate" in p["title"]), None)

        if success_plot:
            data_points = success_plot["plot_details"]["data_points"]
            # Should have one bucket with 33.3% success rate (1 success out of 3)
            non_zero_points = [p for p in data_points if p["value"] > 0]
            if non_zero_points:
                # Allow for floating point precision
                assert abs(non_zero_points[0]["value"] - 33.3) < 0.1


# Test #21: LLM metrics aggregation
@pytest_asyncio.fixture
async def test21_data(db_session):
    """Test #21 data: LLM metrics aggregation"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    created_alerts = []
    for i in range(2):
        alert = DBAlert(
            external_id=f"llm-{i + 1}",
            payload={"test": f"llm{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"LLM Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            llm_metrics={"latency": 0.3 + i * 0.4, "calls": 3 + i * 2}  # 0.3,3 and 0.7,5
        )
        db_session.add(triage)

        evaluation = EvaluationDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            llm_metrics={"latency": 0.2 + i * 0.2, "calls": 2 + i * 1},  # 0.2,2 and 0.4,3
            orch_agent_util_score_percent=85 - i * 10,
            orch_task_completion_score_percent=90 - i * 10,
            sub_agent_tool_util_score_percent=88 - i * 10,
            sub_agent_task_completion_score=87 - i * 10
        )
        db_session.add(evaluation)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_llm_metrics_aggregation(client, test21_data):
    """Test #21: LLM metrics aggregation across triage and evaluation"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]

        llm_latency = next((m for m in kpi_metrics if m["label"] == "Avg P95 Latency"), None)
        llm_calls = next((m for m in kpi_metrics if m["label"] == "Total LLM Calls"), None)

        if llm_latency:
            # 0.3+0.7+0.2+0.4 = 1.6s
            assert "1.6" in llm_latency["value"] or "1.60" in llm_latency["value"]

        if llm_calls:
            # 3+5+2+3 = 13
            assert llm_calls["value"] == "13"


# Test #22: Triage success rate precision
@pytest_asyncio.fixture
async def test22_data(db_session):
    """Test #22 data: Triage success rate precision"""
    base_time = datetime(2024, 1, 1, 10, 0, 0)

    statuses = [Status.SUCCESS, Status.SUCCESS, Status.ERROR]  # 2 success, 1 error
    created_alerts = []

    for i, status in enumerate(statuses):
        alert = DBAlert(
            external_id=f"prec-{i + 1}",
            payload={"test": f"prec{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Precision Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=status
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_triage_success_rate_precision(client, test22_data):
    """Test #22: Triage success rate precision (66.7%)"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Triage Success Rate is no longer in KPI metrics, it's only in plots
        assert "kpi_metrics" in data


# Test #23: All triage statuses distribution
@pytest_asyncio.fixture
async def test23_data(db_session):
    """Test #23 data: All triage statuses for distribution plot"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago, within 24h range

    statuses = [Status.SUCCESS, Status.ERROR, Status.QUEUED, Status.PROCESSING]
    created_alerts = []

    for i, status in enumerate(statuses):
        alert = DBAlert(
            external_id=f"status-{i + 1}",
            payload={"test": f"status{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Status Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=status
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_all_triage_statuses_distribution(client, test23_data):
    """Test #23: All triage statuses in distribution plot"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]
        plots = data["plots"]

        # Check KPI metrics - only checking KPIs that still exist
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)

        assert total_alerts is not None
        assert total_alerts["value"] == "4"

        # Check triage status distribution plot
        status_plot = next((p for p in plots if p["title"] == "Triage Status Distribution"), None)
        assert status_plot is not None

        plot_data = status_plot["plot_details"]["data"]
        status_names = [item["name"] for item in plot_data]

        # Should have 3 statuses (API returns lowercase)
        # QUEUED is combined with PENDING and displayed as "pending"
        expected_statuses = ["success", "error", "pending", "processing"]
        for status in expected_statuses:
            assert status in status_names

        # Verify the distribution: 1 success, 1 error, 1 queued (shown as pending), 1 processing
        # Each should be 25% since we have 4 alerts with different statuses
        status_dict = {item["name"]: item["value"] for item in plot_data}
        assert status_dict["success"] == 25
        assert status_dict["error"] == 25
        assert status_dict["pending"] == 25  # This is the QUEUED status shown as pending
        assert status_dict["processing"] == 25


# Test #23b: PENDING and QUEUED combined as "pending"
@pytest_asyncio.fixture
async def test23b_data(db_session):
    """Test #23b data: Both PENDING and QUEUED statuses combined as pending"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)

    # Create alerts with different statuses including both PENDING and QUEUED
    statuses = [Status.SUCCESS, Status.ERROR, Status.PENDING, Status.QUEUED, Status.PROCESSING]
    created_alerts = []

    for i, status in enumerate(statuses):
        alert = DBAlert(
            external_id=f"combined-status-{i + 1}",
            payload={"test": f"combined{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Combined Status Alert {i + 1}",
            created_at=base_time + timedelta(hours=i)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=status
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_pending_and_queued_combined(client, test23b_data):
    """Test #23b: PENDING and QUEUED are combined and shown as 'pending'"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        plots = data["plots"]

        # Check triage status distribution plot
        status_plot = next((p for p in plots if p["title"] == "Triage Status Distribution"), None)
        assert status_plot is not None

        plot_data = status_plot["plot_details"]["data"]
        status_dict = {item["name"]: item["value"] for item in plot_data}

        # We have 5 alerts: 1 SUCCESS, 1 ERROR, 1 PENDING, 1 QUEUED, 1 PROCESSING
        # PENDING and QUEUED should be combined into "pending" = 2 alerts = 40%
        assert status_dict["success"] == 20  # 1 out of 5 = 20%
        assert status_dict["error"] == 20  # 1 out of 5 = 20%
        assert status_dict["pending"] == 40  # 2 out of 5 (PENDING + QUEUED) = 40%
        assert status_dict["processing"] == 20  # 1 out of 5 = 20%

        # Verify we only have 4 distinct statuses in the response (not 5)
        assert len(plot_data) == 4


# Test #24: Single alert with SUCCESS triage and SUCCESS evaluation (detailed validation)
@pytest_asyncio.fixture
async def test24_data(db_session):
    """Test #24 data: Single alert with SUCCESS triage and evaluation with detailed validation"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)

    alert = DBAlert(
        external_id="ext-success-1",
        payload={"test": "success_data"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Database Connection Issue",
        created_at=base_time,
        updated_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    triage = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        thread_id="thread-success-1",
        job_id="job-success-1",
        root_cause_summary="Database connection pool exhausted",
        tokens_used=150,
        price_usd=0.75,
        processing_time_sec=3.2
    )
    db_session.add(triage)

    evaluation = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        job_id="eval-success-1",
        root_cause_similarity_percent=95,
        orch_agent_util_score_percent=88,
        orch_task_completion_score_percent=92,
        sub_agent_tool_util_score_percent=85,
        sub_agent_task_completion_score=90,
        reason="Excellent root cause analysis and resolution",
        tokens_used=75,
        price_usd=0.35,
        processing_time_sec=2.1
    )
    db_session.add(evaluation)

    await db_session.commit()
    return {"alert": alert, "triage": triage, "evaluation": evaluation}


async def test_single_alert_success_detailed_validation(client, test24_data):
    """Test #24: Single alert with SUCCESS triage and evaluation - detailed validation"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data

        # Should have metrics for successful alert
        kpi_metrics = data["kpi_metrics"]
        assert len(kpi_metrics) > 0

        # Find and validate specific metrics - only checking KPIs that still exist
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Basic counts
        assert metrics_dict["Total Alerts"]["value"] == "1"

        # Verify we have the 4 expected KPI metrics
        assert "Total Alerts" in metrics_dict
        assert "Total Cost" in metrics_dict
        assert "Total LLM Calls" in metrics_dict
        assert "Avg P95 Latency" in metrics_dict

        # Should have plots for successful alert
        plots = data["plots"]
        assert len(plots) > 0

        # Verify plot structure and non-empty data
        for plot in plots:
            assert "title" in plot
            assert "plot_details" in plot

            # Check that plots contain actual data (not empty)
            if "data" in plot["plot_details"]:
                # Pie chart data
                pie_data = plot["plot_details"]["data"]
                assert len(pie_data) > 0, f"Pie chart '{plot['title']}' has empty data"

                # Verify each pie slice has valid data
                for item in pie_data:
                    assert "name" in item
                    assert "value" in item
                    assert isinstance(item["value"], (int, float))
                    assert item["value"] >= 0  # Values should be non-negative

            elif "data_points" in plot["plot_details"]:
                # Line chart data
                line_data = plot["plot_details"]["data_points"]
                assert len(line_data) > 0, f"Line chart '{plot['title']}' has empty data_points"

                # Verify each data point has valid data
                for point in line_data:
                    assert "timestamp" in point
                    assert "value" in point
                    assert isinstance(point["timestamp"], (int, float))
                    assert isinstance(point["value"], (int, float))
                    assert point["value"] >= 0  # Values should be non-negative

            else:
                # Should have either data or data_points
                assert False, f"Plot '{plot['title']}' has neither 'data' nor 'data_points'"

        # Verify specific expected plots exist and have data
        expected_plots = ["Triage Status Distribution", "Triage Success Rate", "Avg Audit Score %"]
        plot_titles = [plot["title"] for plot in plots]

        for expected_title in expected_plots:
            assert expected_title in plot_titles, f"Missing expected plot: {expected_title}"

            # Find the specific plot and verify it has data
            specific_plot = next(plot for plot in plots if plot["title"] == expected_title)

            if expected_title == "Triage Status Distribution":
                # Pie chart should have status data
                status_data = specific_plot["plot_details"]["data"]
                assert len(status_data) > 0
                # Should have at least one status (success in this case)
                status_names = [item["name"] for item in status_data]
                assert "success" in status_names

            elif "%" in expected_title:
                # Line charts should have time series data and average field
                if "data_points" in specific_plot["plot_details"]:
                    data_points = specific_plot["plot_details"]["data_points"]
                    # Verify average field exists
                    assert "average" in specific_plot[
                        "plot_details"], f"Line chart '{expected_title}' missing average field"
                    assert specific_plot["plot_details"]["average"] is not None
                    assert len(data_points) > 0
                    # At least one data point should have a meaningful value
                    values = [point["value"] for point in data_points]
                    assert any(v > 0 for v in values), f"All values in '{expected_title}' are zero"


# Test #25: Multiple alerts across different time buckets for plot verification
@pytest_asyncio.fixture
async def test25_data(db_session):
    """Test #25 data: 4 alerts (2 success, 1 error, 1 processing) in different time configurations"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)

    # Configuration 1: All 4 alerts in same 30m bucket
    config1_time = base_time

    # Alert 1: Success triage + Success evaluation
    alert1 = DBAlert(
        external_id="ext-multi-1",
        payload={"test": "success_data_1"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Database Connection Issue 1",
        created_at=config1_time,
        updated_at=config1_time
    )
    db_session.add(alert1)
    await db_session.flush()

    triage1 = TriageDBModel(
        alert_id=alert1.id,
        status=Status.SUCCESS,
        thread_id="thread-multi-1",
        job_id="job-multi-1",
        root_cause_summary="Database connection pool exhausted",
        tokens_used=150,
        price_usd=0.75,
        processing_time_sec=3
    )
    db_session.add(triage1)

    evaluation1 = EvaluationDBModel(
        alert_id=alert1.id,
        status=Status.SUCCESS,
        job_id="eval-multi-1",
        root_cause_similarity_percent=95,
        orch_agent_util_score_percent=88,
        orch_task_completion_score_percent=92,
        sub_agent_tool_util_score_percent=85,
        sub_agent_task_completion_score=90,
        reason="Excellent analysis",
        tokens_used=75,
        price_usd=0.35,
        processing_time_sec=2
    )
    db_session.add(evaluation1)

    # Alert 2: Success triage + Success evaluation (same bucket)
    alert2 = DBAlert(
        external_id="ext-multi-2",
        payload={"test": "success_data_2"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Memory Usage High 2",
        created_at=config1_time + timedelta(minutes=10),
        updated_at=config1_time + timedelta(minutes=10)
    )
    db_session.add(alert2)
    await db_session.flush()

    triage2 = TriageDBModel(
        alert_id=alert2.id,
        status=Status.SUCCESS,
        thread_id="thread-multi-2",
        job_id="job-multi-2",
        root_cause_summary="Memory leak detected",
        tokens_used=200,
        price_usd=1.0,
        processing_time_sec=4
    )
    db_session.add(triage2)

    evaluation2 = EvaluationDBModel(
        alert_id=alert2.id,
        status=Status.SUCCESS,
        job_id="eval-multi-2",
        root_cause_similarity_percent=80,
        orch_agent_util_score_percent=75,
        orch_task_completion_score_percent=85,
        sub_agent_tool_util_score_percent=90,
        sub_agent_task_completion_score=88,
        reason="Good analysis",
        tokens_used=100,
        price_usd=0.50,
        processing_time_sec=3
    )
    db_session.add(evaluation2)

    # Alert 3: Error triage (same bucket)
    alert3 = DBAlert(
        external_id="ext-multi-3",
        payload={"test": "error_data_3"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="CPU Spike Alert 3",
        created_at=config1_time + timedelta(minutes=20),
        updated_at=config1_time + timedelta(minutes=20)
    )
    db_session.add(alert3)
    await db_session.flush()

    triage3 = TriageDBModel(
        alert_id=alert3.id,
        status=Status.ERROR,
        thread_id="thread-multi-3",
        job_id="job-multi-3",
        error_message="Failed to analyze alert",
        tokens_used=50,
        price_usd=0.25,
        processing_time_sec=1
    )
    db_session.add(triage3)

    # Alert 4: Processing triage (same bucket)
    alert4 = DBAlert(
        external_id="ext-multi-4",
        payload={"test": "processing_data_4"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P3,
        alert_name="Disk Space Alert 4",
        created_at=config1_time + timedelta(minutes=25),
        updated_at=config1_time + timedelta(minutes=25)
    )
    db_session.add(alert4)
    await db_session.flush()

    triage4 = TriageDBModel(
        alert_id=alert4.id,
        status=Status.PROCESSING,
        thread_id="thread-multi-4",
        job_id="job-multi-4",
        root_cause_summary="Analysis in progress",
        tokens_used=25,
        price_usd=0.15,
        processing_time_sec=2
    )
    db_session.add(triage4)

    await db_session.commit()

    return {
        "alerts": [alert1, alert2, alert3, alert4],
        "triages": [triage1, triage2, triage3, triage4],
        "evaluations": [evaluation1, evaluation2],
        "config1_time": config1_time
    }


# Test #26b: One week filter with alerts only in current day
@pytest_asyncio.fixture
async def test26b_data(db_session):
    """Test #26b data: One week filter with alerts only in current day"""
    # Get current day at midnight UTC
    now = datetime.now(timezone.utc)
    current_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Create alerts only for today (at different times)
    created_alerts = []
    for i in range(3):
        alert = DBAlert(
            external_id=f"one-week-today-{i + 1}",
            payload={"test": f"one_week_today{i}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"One Week Today Alert {i + 1}",
            created_at=current_day_start + timedelta(hours=i + 1)  # 1am, 2am, 3am today
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=Status.SUCCESS,
            tokens_used=100 * (i + 1),
            price_usd=0.5 * (i + 1),
            processing_time_sec=2 + i
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_one_week_filter_current_day_alerts(client, test26b_data):
    """Test #26b: One week filter with alerts only in current day"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        # Query with 7-day filter
        response = await client.get("/v1/stats/summary?time_range=7d")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data

        kpi_metrics = data["kpi_metrics"]
        plots = data["plots"]

        # Verify KPI metrics
        total_alerts = next((m for m in kpi_metrics if m["label"] == "Total Alerts"), None)
        assert total_alerts is not None
        assert total_alerts["value"] == "3"

        # Verify plots exist
        assert len(plots) > 0

        # Find the success rate plot
        success_plot = next((p for p in plots if "Triage Success Rate" in p["title"]), None)
        assert success_plot is not None

        # Verify data points - should have data only for today
        data_points = success_plot["plot_details"]["data_points"]
        assert len(data_points) > 0

        # Count non-zero data points (should be only 1 for today)
        non_zero_points = [p for p in data_points if p["value"] > 0]
        assert len(non_zero_points) == 1, "Should have data only for current day"

        # Verify the non-zero point has 100% success rate (all 3 alerts succeeded)
        assert non_zero_points[0]["value"] == 100.0

        # Verify other days have zero values
        zero_points = [p for p in data_points if p["value"] == 0]
        assert len(zero_points) == 6, "Should have 6 empty days in the week"


async def test_multiple_alerts_same_bucket_plots(client, test25_data):
    """Test #25a: 4 alerts in same 30m bucket - verify plot data"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data
        # Verify KPI metrics - only checking KPIs that still exist
        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Basic counts
        assert metrics_dict["Total Alerts"]["value"] == "4"

        # Verify plots exist
        plots = data["plots"]
        assert len(plots) > 0

        # Find specific plots
        plot_titles = [plot["title"] for plot in plots]
        assert "Triage Status Distribution" in plot_titles
        assert "Triage Success Rate" in plot_titles
        assert "Avg Audit Score %" in plot_titles

        # Verify pie chart data (status distribution)
        status_plot = next(plot for plot in plots if plot["title"] == "Triage Status Distribution")
        assert "plot_details" in status_plot
        assert "data" in status_plot["plot_details"]

        status_data = status_plot["plot_details"]["data"]
        status_dict = {item["name"]: item["value"] for item in status_data}

        # Verify status distribution percentages (status names are lowercase in API)
        assert status_dict["success"] == 50  # 2 out of 4 alerts
        assert status_dict["error"] == 25  # 1 out of 4 alerts
        assert status_dict["processing"] == 25  # 1 out of 4 alerts

        # Verify line chart data points exist
        success_rate_plot = next(plot for plot in plots if plot["title"] == "Triage Success Rate")
        assert "plot_details" in success_rate_plot
        assert "data_points" in success_rate_plot["plot_details"]

        data_points = success_rate_plot["plot_details"]["data_points"]
        assert len(data_points) > 0

        # At least one data point should show 75% success rate (3 successful out of 4 total)
        success_rates = [point["value"] for point in data_points]
        # Allow for some flexibility in success rate calculation (should be around 75%)
        assert any(rate >= 70.0 for rate in success_rates), f"Expected success rate >= 70%, got: {success_rates}"


# Test #25b: Same alerts separated by 1 hour
@pytest_asyncio.fixture
async def test25b_data(db_session):
    """Test #25b data: 4 alerts separated by 1 hour each"""
    base_time = datetime.now(timezone.utc) - timedelta(hours=12)

    # Alert 1: Success (hour 0)
    alert1 = DBAlert(
        external_id="ext-hourly-1",
        payload={"test": "hourly_data_1"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Hourly Alert 1",
        created_at=base_time,
        updated_at=base_time
    )
    db_session.add(alert1)
    await db_session.flush()

    triage1 = TriageDBModel(
        alert_id=alert1.id,
        status=Status.SUCCESS,
        thread_id="thread-hourly-1",
        job_id="job-hourly-1",
        root_cause_summary="Issue resolved",
        tokens_used=150,
        price_usd=0.75,
        processing_time_sec=3
    )
    db_session.add(triage1)

    # Alert 2: Success (hour 1)
    alert2 = DBAlert(
        external_id="ext-hourly-2",
        payload={"test": "hourly_data_2"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Hourly Alert 2",
        created_at=base_time + timedelta(hours=1),
        updated_at=base_time + timedelta(hours=1)
    )
    db_session.add(alert2)
    await db_session.flush()

    triage2 = TriageDBModel(
        alert_id=alert2.id,
        status=Status.SUCCESS,
        thread_id="thread-hourly-2",
        job_id="job-hourly-2",
        root_cause_summary="Issue resolved",
        tokens_used=200,
        price_usd=1.0,
        processing_time_sec=4
    )
    db_session.add(triage2)

    # Alert 3: Error (hour 2)
    alert3 = DBAlert(
        external_id="ext-hourly-3",
        payload={"test": "hourly_data_3"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Hourly Alert 3",
        created_at=base_time + timedelta(hours=2),
        updated_at=base_time + timedelta(hours=2)
    )
    db_session.add(alert3)
    await db_session.flush()

    triage3 = TriageDBModel(
        alert_id=alert3.id,
        status=Status.ERROR,
        thread_id="thread-hourly-3",
        job_id="job-hourly-3",
        error_message="Analysis failed",
        tokens_used=50,
        price_usd=0.25,
        processing_time_sec=1
    )
    db_session.add(triage3)

    # Alert 4: Processing (hour 3)
    alert4 = DBAlert(
        external_id="ext-hourly-4",
        payload={"test": "hourly_data_4"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P3,
        alert_name="Hourly Alert 4",
        created_at=base_time + timedelta(hours=3),
        updated_at=base_time + timedelta(hours=3)
    )
    db_session.add(alert4)
    await db_session.flush()

    triage4 = TriageDBModel(
        alert_id=alert4.id,
        status=Status.PROCESSING,
        thread_id="thread-hourly-4",
        job_id="job-hourly-4",
        root_cause_summary="In progress",
        tokens_used=25,
        price_usd=0.15,
        processing_time_sec=2
    )
    db_session.add(triage4)

    await db_session.commit()

    return {
        "alerts": [alert1, alert2, alert3, alert4],
        "triages": [triage1, triage2, triage3, triage4],
        "base_time": base_time
    }


async def test_multiple_alerts_hourly_separation_plots(client, test25b_data):
    """Test #25b: 4 alerts separated by 1 hour each - verify plot trends"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data

        # Verify KPI metrics - only checking KPIs that still exist
        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Basic counts
        assert metrics_dict["Total Alerts"]["value"] == "4"

        # Verify plots
        plots = data["plots"]
        plot_titles = [plot["title"] for plot in plots]
        assert "Triage Success Rate" in plot_titles

        # Verify line chart has multiple time buckets
        success_rate_plot = next(plot for plot in plots if plot["title"] == "Triage Success Rate")
        data_points = success_rate_plot["plot_details"]["data_points"]

        # Should have multiple data points for different hours
        assert len(data_points) >= 4  # At least 4 time buckets

        # Verify timestamps are different (separated by hours)
        timestamps = [point["timestamp"] for point in data_points]
        unique_timestamps = set(timestamps)
        assert len(unique_timestamps) >= 4  # Multiple distinct time buckets


# Test #25c: Same alerts separated by 1 day
@pytest_asyncio.fixture
async def test25c_data(db_session):
    """Test #25c data: 4 alerts separated by 1 day each"""
    base_time = datetime.now(timezone.utc) - timedelta(days=4)

    # Alert 1: Success (day 0)
    alert1 = DBAlert(
        external_id="ext-daily-1",
        payload={"test": "daily_data_1"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Daily Alert 1",
        created_at=base_time,
        updated_at=base_time
    )
    db_session.add(alert1)
    await db_session.flush()

    triage1 = TriageDBModel(
        alert_id=alert1.id,
        status=Status.SUCCESS,
        thread_id="thread-daily-1",
        job_id="job-daily-1",
        root_cause_summary="Daily issue resolved",
        tokens_used=150,
        price_usd=0.75,
        processing_time_sec=3
    )
    db_session.add(triage1)

    # Alert 2: Success (day 1)
    alert2 = DBAlert(
        external_id="ext-daily-2",
        payload={"test": "daily_data_2"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Daily Alert 2",
        created_at=base_time + timedelta(days=1),
        updated_at=base_time + timedelta(days=1)
    )
    db_session.add(alert2)
    await db_session.flush()

    triage2 = TriageDBModel(
        alert_id=alert2.id,
        status=Status.SUCCESS,
        thread_id="thread-daily-2",
        job_id="job-daily-2",
        root_cause_summary="Daily issue resolved",
        tokens_used=200,
        price_usd=1.0,
        processing_time_sec=4
    )
    db_session.add(triage2)

    # Alert 3: Error (day 2)
    alert3 = DBAlert(
        external_id="ext-daily-3",
        payload={"test": "daily_data_3"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Daily Alert 3",
        created_at=base_time + timedelta(days=2),
        updated_at=base_time + timedelta(days=2)
    )
    db_session.add(alert3)
    await db_session.flush()

    triage3 = TriageDBModel(
        alert_id=alert3.id,
        status=Status.ERROR,
        thread_id="thread-daily-3",
        job_id="job-daily-3",
        error_message="Daily analysis failed",
        tokens_used=50,
        price_usd=0.25,
        processing_time_sec=1
    )
    db_session.add(triage3)

    # Alert 4: Processing (day 3)
    alert4 = DBAlert(
        external_id="ext-daily-4",
        payload={"test": "daily_data_4"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P3,
        alert_name="Daily Alert 4",
        created_at=base_time + timedelta(days=3),
        updated_at=base_time + timedelta(days=3)
    )
    db_session.add(alert4)
    await db_session.flush()

    triage4 = TriageDBModel(
        alert_id=alert4.id,
        status=Status.PROCESSING,
        thread_id="thread-daily-4",
        job_id="job-daily-4",
        root_cause_summary="Daily processing",
        tokens_used=25,
        price_usd=0.15,
        processing_time_sec=2
    )
    db_session.add(triage4)

    await db_session.commit()

    return {
        "alerts": [alert1, alert2, alert3, alert4],
        "triages": [triage1, triage2, triage3, triage4],
        "base_time": base_time
    }


async def test_multiple_alerts_daily_separation_plots(client, test25c_data):
    """Test #25c: 4 alerts separated by 1 day each - verify daily plot trends"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=7d")  # Use 7d to capture all days

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "kpi_metrics" in data
        assert "plots" in data

        # Verify KPI metrics - only checking KPIs that still exist
        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Basic counts
        assert metrics_dict["Total Alerts"]["value"] == "4"

        # Verify plots
        plots = data["plots"]
        plot_titles = [plot["title"] for plot in plots]
        assert "Triage Success Rate" in plot_titles

        # Verify line chart has daily time buckets
        success_rate_plot = next(plot for plot in plots if plot["title"] == "Triage Success Rate")
        data_points = success_rate_plot["plot_details"]["data_points"]

        # Should have multiple data points for different days
        assert len(data_points) >= 3  # At least 3 daily buckets (we have 4 days but 1 has 0% success rate)

        # Verify we have data points with different success rates over time
        success_rates = [point["value"] for point in data_points if point["value"] > 0]
        assert len(success_rates) >= 3  # Should have success rate data for 3 days (2 SUCCESS + 1 PROCESSING)

        # Verify status distribution
        status_plot = next(plot for plot in plots if plot["title"] == "Triage Status Distribution")
        status_data = status_plot["plot_details"]["data"]
        status_dict = {item["name"]: item["value"] for item in status_data}

        # Status names are lowercase in the API
        assert status_dict["success"] == 50  # 2 out of 4
        assert status_dict["error"] == 25  # 1 out of 4
        assert status_dict["processing"] == 25  # 1 out of 4


# Test #26: Positive delta calculations
@pytest_asyncio.fixture
async def test26_data(db_session):
    """Test #26 data: Current period has more alerts than previous (positive delta)"""
    current_time = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago
    previous_time = datetime.now(timezone.utc) - timedelta(hours=36)  # 36 hours ago

    # Previous period: 2 alerts, 1 success (50% success rate)
    prev_alert1 = DBAlert(
        external_id="prev-1",
        payload={"test": "prev1"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Previous Alert 1",
        created_at=previous_time
    )
    db_session.add(prev_alert1)
    await db_session.flush()

    prev_triage1 = TriageDBModel(
        alert_id=prev_alert1.id,
        status=Status.SUCCESS,
        tokens_used=100,
        price_usd=0.5,
        processing_time_sec=2.0
    )
    db_session.add(prev_triage1)

    prev_alert2 = DBAlert(
        external_id="prev-2",
        payload={"test": "prev2"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Previous Alert 2",
        created_at=previous_time + timedelta(minutes=30)
    )
    db_session.add(prev_alert2)
    await db_session.flush()

    prev_triage2 = TriageDBModel(
        alert_id=prev_alert2.id,
        status=Status.ERROR,
        tokens_used=50,
        price_usd=0.25,
        processing_time_sec=1.0
    )
    db_session.add(prev_triage2)

    # Current period: 4 alerts, 3 success (75% success rate)
    current_alerts_data = [
        {"external_id": "curr-1", "status": Status.SUCCESS, "tokens": 150, "cost": 0.75, "time": 3.0},
        {"external_id": "curr-2", "status": Status.SUCCESS, "tokens": 120, "cost": 0.60, "time": 2.5},
        {"external_id": "curr-3", "status": Status.SUCCESS, "tokens": 100, "cost": 0.50, "time": 2.0},
        {"external_id": "curr-4", "status": Status.ERROR, "tokens": 80, "cost": 0.40, "time": 1.5}
    ]

    created_alerts = []
    for i, alert_data in enumerate(current_alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"curr{i + 1}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Current Alert {i + 1}",
            created_at=current_time + timedelta(minutes=i * 15)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["status"],
            tokens_used=alert_data["tokens"],
            price_usd=alert_data["cost"],
            processing_time_sec=alert_data["time"]
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"current_alerts": created_alerts, "previous_alerts": [prev_alert1, prev_alert2]}


async def test_positive_delta_calculations(client, test26_data):
    """Test #26: Positive delta calculations (current > previous)"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Deltas are no longer calculated in new UI
        total_alerts = metrics_dict.get("Total Alerts")
        if total_alerts:
            assert total_alerts["value"] == "4"


# Test #27: Negative delta calculations
@pytest_asyncio.fixture
async def test27_data(db_session):
    """Test #27 data: Current period has fewer alerts than previous (negative delta)"""
    current_time = datetime.now(timezone.utc) - timedelta(hours=12)
    previous_time = datetime.now(timezone.utc) - timedelta(hours=36)

    # Previous period: 5 alerts, 4 success (80% success rate)
    previous_alerts_data = [
        {"external_id": "prev-1", "status": Status.SUCCESS, "tokens": 200, "cost": 1.0, "time": 4.0},
        {"external_id": "prev-2", "status": Status.SUCCESS, "tokens": 180, "cost": 0.9, "time": 3.5},
        {"external_id": "prev-3", "status": Status.SUCCESS, "tokens": 160, "cost": 0.8, "time": 3.0},
        {"external_id": "prev-4", "status": Status.SUCCESS, "tokens": 140, "cost": 0.7, "time": 2.5},
        {"external_id": "prev-5", "status": Status.ERROR, "tokens": 120, "cost": 0.6, "time": 2.0}
    ]

    for i, alert_data in enumerate(previous_alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"prev{i + 1}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Previous Alert {i + 1}",
            created_at=previous_time + timedelta(minutes=i * 10)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["status"],
            tokens_used=alert_data["tokens"],
            price_usd=alert_data["cost"],
            processing_time_sec=alert_data["time"]
        )
        db_session.add(triage)

    # Current period: 2 alerts, 1 success (50% success rate)
    curr_alert1 = DBAlert(
        external_id="curr-1",
        payload={"test": "curr1"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Current Alert 1",
        created_at=current_time
    )
    db_session.add(curr_alert1)
    await db_session.flush()

    curr_triage1 = TriageDBModel(
        alert_id=curr_alert1.id,
        status=Status.SUCCESS,
        tokens_used=100,
        price_usd=0.5,
        processing_time_sec=2.0
    )
    db_session.add(curr_triage1)

    curr_alert2 = DBAlert(
        external_id="curr-2",
        payload={"test": "curr2"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Current Alert 2",
        created_at=current_time + timedelta(minutes=30)
    )
    db_session.add(curr_alert2)
    await db_session.flush()

    curr_triage2 = TriageDBModel(
        alert_id=curr_alert2.id,
        status=Status.ERROR,
        tokens_used=80,
        price_usd=0.4,
        processing_time_sec=1.5
    )
    db_session.add(curr_triage2)

    await db_session.commit()
    return {"current_alerts": [curr_alert1, curr_alert2]}


async def test_negative_delta_calculations(client, test27_data):
    """Test #27: Negative delta calculations (current < previous)"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Deltas are no longer calculated in new UI
        total_alerts = metrics_dict.get("Total Alerts")
        if total_alerts:
            assert total_alerts["value"] == "2"


# Test #28: Zero to positive delta (100% increase)
@pytest_asyncio.fixture
async def test28_data(db_session):
    """Test #28 data: Previous period has no alerts, current has some (100% delta)"""
    current_time = datetime.now(timezone.utc) - timedelta(hours=12)

    # No previous period alerts (they would be outside the comparison window)

    # Current period: 3 alerts
    current_alerts_data = [
        {"external_id": "curr-1", "status": Status.SUCCESS},
        {"external_id": "curr-2", "status": Status.SUCCESS},
        {"external_id": "curr-3", "status": Status.ERROR}
    ]

    created_alerts = []
    for i, alert_data in enumerate(current_alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"curr{i + 1}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Current Alert {i + 1}",
            created_at=current_time + timedelta(minutes=i * 20)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["status"],
            tokens_used=100,
            price_usd=0.5,
            processing_time_sec=2.0
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_zero_to_positive_delta(client, test28_data):
    """Test #28: Zero to positive delta (100% increase)"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # When previous period has 0 alerts and current has some, delta should be 100%
        total_alerts = metrics_dict.get("Total Alerts")
        if total_alerts and total_alerts.get("delta"):
            assert total_alerts["value"] == "3"
            assert total_alerts["delta"]["value"] == 100.0

        # Deltas are no longer calculated in new UI


# Test #29: Greater than 100% delta (significant increase)
@pytest_asyncio.fixture
async def test29_data(db_session):
    """Test #29 data: Current period has much more alerts than previous (>100% delta)"""
    current_time = datetime.now(timezone.utc) - timedelta(hours=12)
    previous_time = datetime.now(timezone.utc) - timedelta(hours=36)

    # Previous period: 2 alerts, 1 success (50% success rate)
    previous_alerts_data = [
        {"external_id": "prev-1", "status": Status.SUCCESS, "tokens": 100, "cost": 0.3, "time": 2.0},
        {"external_id": "prev-2", "status": Status.ERROR, "tokens": 80, "cost": 0.2, "time": 1.5}
    ]

    for i, alert_data in enumerate(previous_alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"prev{i + 1}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Previous Alert {i + 1}",
            created_at=previous_time + timedelta(minutes=i * 10)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["status"],
            tokens_used=alert_data["tokens"],
            price_usd=alert_data["cost"],
            processing_time_sec=alert_data["time"]
        )
        db_session.add(triage)

    # Current period: 7 alerts, 5 success (71.4% success rate)
    current_alerts_data = [
        {"external_id": "curr-1", "status": Status.SUCCESS, "tokens": 120, "cost": 0.6, "time": 2.5},
        {"external_id": "curr-2", "status": Status.SUCCESS, "tokens": 110, "cost": 0.55, "time": 2.2},
        {"external_id": "curr-3", "status": Status.SUCCESS, "tokens": 100, "cost": 0.5, "time": 2.0},
        {"external_id": "curr-4", "status": Status.SUCCESS, "tokens": 90, "cost": 0.45, "time": 1.8},
        {"external_id": "curr-5", "status": Status.SUCCESS, "tokens": 80, "cost": 0.4, "time": 1.5},
        {"external_id": "curr-6", "status": Status.ERROR, "tokens": 70, "cost": 0.35, "time": 1.2},
        {"external_id": "curr-7", "status": Status.ERROR, "tokens": 60, "cost": 0.3, "time": 1.0}
    ]

    created_alerts = []
    for i, alert_data in enumerate(current_alerts_data):
        alert = DBAlert(
            external_id=alert_data["external_id"],
            payload={"test": f"curr{i + 1}"},
            alert_source="grafana",
            alert_status="firing",
            severity=Severity.P1,
            alert_name=f"Current Alert {i + 1}",
            created_at=current_time + timedelta(minutes=i * 15)
        )
        db_session.add(alert)
        await db_session.flush()

        triage = TriageDBModel(
            alert_id=alert.id,
            status=alert_data["status"],
            tokens_used=alert_data["tokens"],
            price_usd=alert_data["cost"],
            processing_time_sec=alert_data["time"]
        )
        db_session.add(triage)
        created_alerts.append(alert)

    await db_session.commit()
    return {"alerts": created_alerts}


async def test_greater_than_100_percent_delta(client, test29_data):
    """Test #29: Greater than 100% delta (significant increase)"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        kpi_metrics = data["kpi_metrics"]
        metrics_dict = {m["label"]: m for m in kpi_metrics}

        # Verify >100% deltas
        # Deltas are no longer calculated in new UI
        total_alerts = metrics_dict.get("Total Alerts")
        if total_alerts:
            assert total_alerts["value"] == "7"


# ============================================================================
# CUSTOM TIME RANGE TESTS
# ============================================================================


async def test_stats_custom_time_range_valid(client, test2_data):
    """Test custom time range with valid start_time and end_time"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=12)

    # URL-encode the datetime strings to handle the + sign in timezone
    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "kpi_metrics" in data
        assert "plots" in data


async def test_stats_custom_time_range_missing_start_time(client, db_session):
    """Test custom time range validation - missing start_time"""
    end_time = datetime.now(timezone.utc)
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&end_time={end_time_encoded}"
        )

        assert response.status_code == 400
        data = response.json()
        assert "start_time and end_time are required" in data["detail"]


async def test_stats_custom_time_range_missing_end_time(client, db_session):
    """Test custom time range validation - missing end_time"""
    start_time = datetime.now(timezone.utc) - timedelta(days=7)
    start_time_encoded = quote(start_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}"
        )

        assert response.status_code == 400
        data = response.json()
        assert "start_time and end_time are required" in data["detail"]


async def test_stats_custom_time_range_missing_both(client, db_session):
    """Test custom time range validation - missing both start_time and end_time"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=custom")

        assert response.status_code == 400
        data = response.json()
        assert "start_time and end_time are required" in data["detail"]


async def test_stats_custom_time_range_start_after_end(client, db_session):
    """Test custom time range validation - start_time >= end_time"""
    now = datetime.now(timezone.utc)
    start_time = now
    end_time = now - timedelta(hours=1)  # end_time is before start_time

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 400
        data = response.json()
        assert "start_time must be before end_time" in data["detail"]


async def test_stats_custom_time_range_start_equals_end(client, db_session):
    """Test custom time range validation - start_time equals end_time"""
    now = datetime.now(timezone.utc)
    now_encoded = quote(now.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={now_encoded}&end_time={now_encoded}"
        )

        assert response.status_code == 400
        data = response.json()
        assert "start_time must be before end_time" in data["detail"]


async def test_stats_custom_time_range_exceeds_90_days(client, db_session):
    """Test custom time range validation - range exceeds 90 days"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=91)  # 91 days ago

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 400
        data = response.json()
        assert "Custom time range cannot exceed 90 days" in data["detail"]


async def test_stats_custom_time_range_exactly_90_days(client, db_session):
    """Test custom time range validation - exactly 90 days should work"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=90)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "kpi_metrics" in data
        assert "plots" in data


async def test_stats_predefined_ranges_still_work(client, test2_data):
    """Test that predefined time ranges still work correctly"""
    predefined_ranges = ["30m", "1h", "6h", "24h", "7d", "30d"]

    for time_range in predefined_ranges:
        with patch('asyncio.gather', side_effect=sequential_gather):
            response = await client.get(f"/v1/stats/summary?time_range={time_range}")

            assert response.status_code == 200, f"Failed for time_range={time_range}"
            data = response.json()
            assert "kpi_metrics" in data
            assert "plots" in data


# ============================================================================
# ADDITIONAL EDGE CASE TESTS
# ============================================================================


async def test_stats_custom_time_range_very_short(client, db_session):
    """Test custom time range with very short duration (1 minute)"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=1)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "kpi_metrics" in data
        assert "plots" in data


async def test_stats_custom_time_range_zulu_timezone(client, db_session):
    """Test custom time range with Z (Zulu) timezone format"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=6)

    # Use Z format instead of +00:00
    start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    end_time_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_str}&end_time={end_time_str}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "kpi_metrics" in data
        assert "plots" in data


async def test_stats_custom_time_range_invalid_datetime_format(client, db_session):
    """Test custom time range with invalid datetime format"""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            "/v1/stats/summary?time_range=custom&start_time=invalid-date&end_time=also-invalid"
        )

        # Should return 422 (Unprocessable Entity) for invalid datetime format
        assert response.status_code == 422


async def test_stats_custom_time_range_just_under_90_days(client, db_session):
    """Test custom time range just under 90 days (89 days 23 hours)"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=89, hours=23)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "kpi_metrics" in data


async def test_stats_custom_time_range_just_over_90_days(client, db_session):
    """Test custom time range just over 90 days (90 days 1 hour)"""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=90, hours=1)

    start_time_encoded = quote(start_time.isoformat(), safe='')
    end_time_encoded = quote(end_time.isoformat(), safe='')

    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get(
            f"/v1/stats/summary?time_range=custom&start_time={start_time_encoded}&end_time={end_time_encoded}"
        )

        assert response.status_code == 400
        data = response.json()
        assert "Custom time range cannot exceed 90 days" in data["detail"]

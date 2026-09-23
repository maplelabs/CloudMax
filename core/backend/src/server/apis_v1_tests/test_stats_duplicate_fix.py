"""
Unit tests to verify fixes for duplicate alert counting and cartesian product issues.

Tests verify:
1. Alerts with multiple triages are counted only once (latest triage)
2. Metrics calculations don't have cartesian product when joining triages and evaluations
3. Never-triaged alerts (NULL status) are included in status distribution
4. Status distribution includes actual counts alongside percentages
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio

from src.server.models.api.enums import Status, Severity
from src.server.models.db.alert import Alert as DBAlert
from src.server.models.db.evaluation import Evaluation as EvaluationDBModel
from src.server.models.db.triage import Triage as TriageDBModel

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def sequential_gather(*aws, **kwargs):
    """Replacement for asyncio.gather that runs awaitables sequentially."""
    results = []
    for aw in aws:
        result = await aw
        results.append(result)
    return results


# Test #1: Alert with multiple triages should be counted only once (latest triage)
@pytest_asyncio.fixture
async def alert_with_multiple_triages(db_session):
    """Create alert with 3 triage records to test duplicate counting fix."""
    base_time = datetime.utcnow()

    alert = DBAlert(
        external_id="multi-triage-alert",
        payload={"test": "multiple triages"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Multi-Triage Alert",
        created_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    # First triage - ERROR (oldest)
    triage1 = TriageDBModel(
        alert_id=alert.id,
        status=Status.ERROR,
        price_usd=Decimal('1.0'),
        tokens_used=1000,
        processing_time_sec=10,
        created_at=base_time
    )
    db_session.add(triage1)

    # Second triage - PROCESSING (middle)
    triage2 = TriageDBModel(
        alert_id=alert.id,
        status=Status.PROCESSING,
        price_usd=Decimal('2.0'),
        tokens_used=2000,
        processing_time_sec=20,
        created_at=base_time + timedelta(minutes=5)
    )
    db_session.add(triage2)

    # Third triage - SUCCESS (latest - should be counted)
    triage3 = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        price_usd=Decimal('3.0'),
        tokens_used=3000,
        processing_time_sec=30,
        created_at=base_time + timedelta(minutes=10)
    )
    db_session.add(triage3)

    await db_session.commit()
    return {"alert": alert, "triages": [triage1, triage2, triage3], "latest_triage": triage3}


async def test_multiple_triages_counted_once(client, alert_with_multiple_triages):
    """Test that alert with 3 triages is counted only once with latest status."""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Find status distribution plot
        status_dist = None
        for plot in data["plots"]:
            if plot["title"] == "Triage Status Distribution":
                status_dist = plot
                break

        assert status_dist is not None, f"Status distribution plot not found. Available plots: {[p['title'] for p in data['plots']]}"

        # Should only have 1 alert counted with SUCCESS status
        success_items = [item for item in status_dist["plot_details"]["data"] if item["name"] == Status.SUCCESS.value]
        assert len(success_items) == 1
        assert success_items[0]["count"] == 1, "Alert should be counted only once"

        # Total count across all statuses should be 1 (not 3)
        total_count = sum(item["count"] for item in status_dist["plot_details"]["data"])
        assert total_count == 1, f"Expected 1 alert total, got {total_count}"


# Test #2: Cartesian product fix - alert with multiple triages AND evaluations
@pytest_asyncio.fixture
async def alert_with_multiple_triages_and_evals(db_session):
    """Create alert with 2 triages and 2 evaluations to test cartesian product fix."""
    base_time = datetime.utcnow()

    alert = DBAlert(
        external_id="cartesian-test-alert",
        payload={"test": "cartesian product"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Cartesian Test Alert",
        created_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    # Two triages with different costs
    triage1 = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        price_usd=Decimal('1.0780'),  # Real cost from alert 21
        tokens_used=500000,
        processing_time_sec=100,
        created_at=base_time
    )
    db_session.add(triage1)



    triage2 = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        price_usd=Decimal('2.0'),
        tokens_used=600000,
        processing_time_sec=150,
        created_at=base_time + timedelta(minutes=5)
    )
    db_session.add(triage2)

    # Two evaluations with different costs
    eval1 = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        price_usd=Decimal('0.3385'),  # Real cost from alert 21
        tokens_used=100000,
        processing_time_sec=50,
        created_at=base_time
    )
    db_session.add(eval1)

    eval2 = EvaluationDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        price_usd=Decimal('0.5'),
        tokens_used=150000,
        processing_time_sec=75,
        created_at=base_time + timedelta(minutes=5)
    )
    db_session.add(eval2)

    await db_session.commit()

    # Expected cost WITHOUT cartesian product fix: (1.0780 + 2.0) * (0.3385 + 0.5) = 2.5806
    # Expected cost WITH fix: (1.0780 + 2.0) + (0.3385 + 0.5) = 3.9165
    expected_triage_cost = Decimal('1.0780') + Decimal('2.0')
    expected_eval_cost = Decimal('0.3385') + Decimal('0.5')
    expected_total = expected_triage_cost + expected_eval_cost

    return {
        "alert": alert,
        "expected_total_cost": float(expected_total),
        "expected_triage_cost": float(expected_triage_cost),
        "expected_eval_cost": float(expected_eval_cost)
    }


async def test_no_cartesian_product_in_metrics(client, alert_with_multiple_triages_and_evals):
    """Test that costs are summed correctly without cartesian product multiplication."""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Find Total Cost KPI
        total_cost_kpi = None
        for kpi in data["kpi_metrics"]:
            if kpi["label"] == "Total Cost":
                total_cost_kpi = kpi
                break

        assert total_cost_kpi is not None, "Total Cost KPI not found"

        # Extract numeric value (remove $ and convert to float)
        actual_cost = float(total_cost_kpi["value"].replace("$", ""))
        expected_cost = alert_with_multiple_triages_and_evals["expected_total_cost"]

        # Should be sum (3.9165), NOT product (2.5806)
        assert abs(actual_cost - expected_cost) < 0.01, \
            f"Expected cost ${expected_cost:.4f}, got ${actual_cost:.4f}. " \
            f"This suggests cartesian product issue!"


# Test #3: Never-triaged alerts (NULL status) should appear in status distribution
@pytest_asyncio.fixture
async def alerts_with_never_triaged(db_session):
    """Create 2 never-triaged alerts and 1 triaged alert."""
    base_time = datetime.utcnow()

    # Alert 1: Never triaged (no triage record)
    alert1 = DBAlert(
        external_id="never-triaged-1",
        payload={"test": "no triage"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Never Triaged 1",
        created_at=base_time
    )
    db_session.add(alert1)

    # Alert 2: Never triaged (no triage record)
    alert2 = DBAlert(
        external_id="never-triaged-2",
        payload={"test": "no triage"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Never Triaged 2",
        created_at=base_time + timedelta(minutes=5)
    )
    db_session.add(alert2)

    # Alert 3: Successfully triaged
    alert3 = DBAlert(
        external_id="triaged-alert",
        payload={"test": "triaged"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P3,
        alert_name="Triaged Alert",
        created_at=base_time + timedelta(minutes=10)
    )
    db_session.add(alert3)
    await db_session.flush()

    triage3 = TriageDBModel(
        alert_id=alert3.id,
        status=Status.SUCCESS,
        price_usd=Decimal('1.5'),
        tokens_used=5000,
        processing_time_sec=50
    )
    db_session.add(triage3)

    await db_session.commit()
    return {"never_triaged_count": 2, "triaged_count": 1}


async def test_never_triaged_alerts_in_status_distribution(client, alerts_with_never_triaged):
    """Test that never-triaged alerts (NULL status) appear as 'pending' in status distribution."""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Find status distribution plot
        status_dist = None
        for plot in data["plots"]:
            if plot["title"] == "Triage Status Distribution":
                status_dist = plot
                break

        assert status_dist is not None, "Status distribution plot not found"

        # Should have pending status (which includes never-triaged/NULL)
        pending_items = [item for item in status_dist["plot_details"]["data"]
                        if item["name"] == Status.PENDING.value]

        assert len(pending_items) == 1, "Should have pending category"
        assert pending_items[0]["count"] == 2, \
            f"Expected 2 never-triaged alerts in pending, got {pending_items[0]['count']}"

        # Should have success status
        success_items = [item for item in status_dist["plot_details"]["data"]
                        if item["name"] == Status.SUCCESS.value]
        assert len(success_items) == 1, "Should have success category"
        assert success_items[0]["count"] == 1, \
            f"Expected 1 triaged alert in success, got {success_items[0]['count']}"

        # Total should be 3
        total_count = sum(item["count"] for item in status_dist["plot_details"]["data"])
        assert total_count == 3, f"Expected 3 alerts total, got {total_count}"



# Test #4: Status distribution should have 'count' field
@pytest_asyncio.fixture
async def simple_alert_for_count_test(db_session):
    """Create a simple alert to test count field in status distribution."""
    base_time = datetime.utcnow()

    alert = DBAlert(
        external_id="count-field-test",
        payload={"test": "count field"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Count Field Test",
        created_at=base_time
    )
    db_session.add(alert)
    await db_session.flush()

    triage = TriageDBModel(
        alert_id=alert.id,
        status=Status.SUCCESS,
        price_usd=Decimal('1.0'),
        tokens_used=1000,
        processing_time_sec=10
    )
    db_session.add(triage)

    await db_session.commit()
    return {"alert": alert}


async def test_status_distribution_has_count_field(client, simple_alert_for_count_test):
    """Test that status distribution items have 'count' field alongside 'value' (percentage)."""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Find status distribution plot
        status_dist = None
        for plot in data["plots"]:
            if plot["title"] == "Triage Status Distribution":
                status_dist = plot
                break

        assert status_dist is not None, "Status distribution plot not found"

        # Each item should have both 'count' and 'value' fields
        for item in status_dist["plot_details"]["data"]:
            assert "count" in item, f"Missing 'count' field in {item['name']}"
            assert "value" in item, f"Missing 'value' field (percentage) in {item['name']}"
            assert isinstance(item["count"], int), f"'count' should be integer, got {type(item['count'])}"
            assert isinstance(item["value"], int), f"'value' should be integer (percentage), got {type(item['value'])}"

            # For this single alert, percentage should be 100 and count should be 1
            if item["name"] == Status.SUCCESS.value:
                assert item["count"] == 1, f"Expected count=1, got {item['count']}"
                assert item["value"] == 100, f"Expected value=100%, got {item['value']}"


# Test #5: Edge case - alert with QUEUED status should be combined with PENDING
@pytest_asyncio.fixture
async def alerts_with_queued_and_pending(db_session):
    """Create alerts with QUEUED and PENDING statuses to test combination."""
    base_time = datetime.utcnow()

    # Alert 1: QUEUED
    alert1 = DBAlert(
        external_id="queued-alert",
        payload={"test": "queued"},
        alert_source="grafana",
        alert_status="firing",
        severity=Severity.P1,
        alert_name="Queued Alert",
        created_at=base_time
    )
    db_session.add(alert1)
    await db_session.flush()

    triage1 = TriageDBModel(
        alert_id=alert1.id,
        status=Status.QUEUED,
        price_usd=Decimal('0.5'),
        tokens_used=500,
        processing_time_sec=5
    )
    db_session.add(triage1)

    # Alert 2: PENDING
    alert2 = DBAlert(
        external_id="pending-alert",
        payload={"test": "pending"},
        alert_source="prometheus",
        alert_status="firing",
        severity=Severity.P2,
        alert_name="Pending Alert",
        created_at=base_time + timedelta(minutes=5)
    )
    db_session.add(alert2)
    await db_session.flush()

    triage2 = TriageDBModel(
        alert_id=alert2.id,
        status=Status.PENDING,
        price_usd=Decimal('0.5'),
        tokens_used=500,
        processing_time_sec=5
    )
    db_session.add(triage2)

    await db_session.commit()
    return {"queued_count": 1, "pending_count": 1, "combined_count": 2}


async def test_queued_and_pending_combined(client, alerts_with_queued_and_pending):
    """Test that QUEUED and PENDING statuses are combined into single 'pending' category."""
    with patch('asyncio.gather', side_effect=sequential_gather):
        response = await client.get("/v1/stats/summary?time_range=24h")

        assert response.status_code == 200
        data = response.json()

        # Find status distribution plot
        status_dist = None
        for plot in data["plots"]:
            if plot["title"] == "Triage Status Distribution":
                status_dist = plot
                break

        assert status_dist is not None, "Status distribution plot not found"

        # Should NOT have QUEUED as a separate category
        queued_items = [item for item in status_dist["plot_details"]["data"]
                       if item["name"] == Status.QUEUED.value]
        assert len(queued_items) == 0, "QUEUED should not appear as separate category"

        # Should have PENDING with combined count of 2
        pending_items = [item for item in status_dist["plot_details"]["data"]
                        if item["name"] == Status.PENDING.value]
        assert len(pending_items) == 1, "Should have pending category"
        assert pending_items[0]["count"] == 2, \
            f"Expected 2 alerts (QUEUED+PENDING combined), got {pending_items[0]['count']}"

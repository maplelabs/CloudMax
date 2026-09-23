"""
Agent Stats Service API endpoints.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, case, Integer, Numeric, literal, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_db_session, get_current_user
from src.server.models.api.alert_list import validate_custom_time_range
from src.server.models.api.enums import Status, Timeline
from src.server.models.api.overview_stats import (KpiMetric, StatusDistributionItem, TimeSeriesDataPoint,
                                                  PieChartDetail, LineChartDetail, PlotConfig, OverviewStatsRequest,
                                                  OverviewStatsResponse)
from src.server.models.db.alert import Alert as AlertDbModel
from src.server.models.db.evaluation import Evaluation as EvaluationDbModel
from src.server.models.db.triage import Triage as TriageDbModel
from src.server.utilities.config import is_chaos_system_enabled

logger = logging.getLogger(__name__)
router = APIRouter()


def build_kpi_counts_query(start_time: datetime, end_time: datetime = None):
    """
    Build query to get alert and triage counts grouped by severity and status.
    Only counts the latest triage per alert to avoid counting alerts multiple times.

    CRITICAL: Handles both grouped and ungrouped alerts correctly:
    - For ungrouped alerts: uses triages.status
    - For grouped alerts: uses alert_groups.triage_status (placeholder triages are ignored)

    Returns: status, alert_count
    """
    from src.server.models.db import AlertGroupDBModel

    # Create a subquery to get the latest triage record per alert using window function
    latest_triage_subquery = (
        select(
            TriageDbModel.alert_id,
            TriageDbModel.status,
            func.row_number().over(
                partition_by=TriageDbModel.alert_id,
                order_by=TriageDbModel.created_at.desc()
            ).label('rn')
        )
        .select_from(TriageDbModel)
    ).subquery()

    # Filter to only the latest triage per alert (rn=1)
    latest_triage_cte = (
        select(
            latest_triage_subquery.c.alert_id,
            latest_triage_subquery.c.status
        ).where(
            latest_triage_subquery.c.rn == 1
        )
    ).subquery()

    # Calculate the effective triage status for each alert:
    # - If alert is in a group (group_id IS NOT NULL): use group's triage_status
    # - If alert is ungrouped (group_id IS NULL): use individual triage status
    # Map group triage_status (completed, in_progress, failed, pending) to API Status enum
    # Cast to text to avoid enum type mismatch between alert_groups.triage_status (varchar) and triages.status (enum)
    effective_status = case(
        # If alert is in a group, map group's triage_status to API Status
        (
            AlertDbModel.group_id.isnot(None),
            case(
                (AlertGroupDBModel.triage_status == 'completed', literal('success')),
                (AlertGroupDBModel.triage_status == 'in_progress', literal('processing')),
                (AlertGroupDBModel.triage_status == 'failed', literal('error')),
                else_=literal('pending')  # pending or any other status
            )
        ),
        # If alert is ungrouped, use individual triage status (cast enum to string)
        else_=func.cast(latest_triage_cte.c.status, String)
    ).label('effective_status')

    # Join alerts with their latest triage and groups, then count by effective status
    query = select(
        effective_status,
        func.count(AlertDbModel.id).label("alert_count")
    ).select_from(
        AlertDbModel
    ).join(
        latest_triage_cte,
        latest_triage_cte.c.alert_id == AlertDbModel.id,
        isouter=True
    ).outerjoin(
        AlertGroupDBModel,
        AlertGroupDBModel.id == AlertDbModel.group_id
    ).group_by(
        effective_status
    )

    if end_time:
        query = query.where(
            (AlertDbModel.created_at >= start_time) & (AlertDbModel.created_at < end_time)
        )
    else:
        query = query.where(AlertDbModel.created_at >= start_time)

    return query


def build_kpi_metrics_query(start_time: datetime, end_time: datetime = None):
    """
    Build query to get KPI metrics from both individual triages and group triages.

    For ungrouped alerts: Uses triages table
    For grouped alerts: Uses alert_groups table (since individual triage records are placeholders)

    Returns: total_cost, avg_p95_latency_sec, total_llm_calls
    """
    # Build time filter for reuse
    time_filter_alert = AlertDbModel.created_at >= start_time
    if end_time:
        time_filter_alert = (AlertDbModel.created_at >= start_time) & (AlertDbModel.created_at < end_time)

    # Query metrics from INDIVIDUAL triages (ungrouped alerts only)
    # Exclude triages for alerts that are part of a group (group_id IS NOT NULL)
    # because those metrics are stored at the group level
    individual_query = (
        select(
            func.sum(func.coalesce(TriageDbModel.price_usd, 0)).label('individual_triage_cost'),
            func.sum(func.coalesce(EvaluationDbModel.price_usd, 0)).label('individual_eval_cost'),
            func.sum(
                func.coalesce(
                    func.cast(TriageDbModel.llm_metrics['total_llm_calls'].astext, Integer),
                    0
                )
            ).label('individual_triage_llm_calls'),
            func.sum(
                func.coalesce(
                    func.cast(EvaluationDbModel.llm_metrics['total_llm_calls'].astext, Integer),
                    0
                )
            ).label('individual_eval_llm_calls'),
            func.avg(
                func.coalesce(
                    func.cast(TriageDbModel.llm_metrics['p95_latency_sec'].astext, Numeric),
                    0
                )
            ).label('individual_avg_p95_latency')
        )
        .select_from(AlertDbModel)
        .join(TriageDbModel, TriageDbModel.alert_id == AlertDbModel.id)
        .outerjoin(
            EvaluationDbModel,
            (EvaluationDbModel.alert_id == AlertDbModel.id) & (EvaluationDbModel.status == Status.SUCCESS)
        )
        .where(time_filter_alert)
        .where(AlertDbModel.group_id.is_(None))  # Only ungrouped alerts
    ).subquery()

    # Query metrics from GROUP triages and evaluations
    # Group triage metrics are in alert_groups table
    # Group evaluation metrics are in evaluations table with group_id
    from src.server.models.db import AlertGroupDBModel

    group_query = (
        select(
            # Group triage cost
            func.sum(func.coalesce(AlertGroupDBModel.price_usd, 0)).label('group_triage_cost'),
            # Group evaluation cost
            func.sum(func.coalesce(EvaluationDbModel.price_usd, 0)).label('group_eval_cost'),
            # Group triage LLM calls
            func.sum(
                func.coalesce(
                    func.cast(AlertGroupDBModel.llm_metrics['total_llm_calls'].astext, Integer),
                    0
                )
            ).label('group_triage_llm_calls'),
            # Group evaluation LLM calls
            func.sum(
                func.coalesce(
                    func.cast(EvaluationDbModel.llm_metrics['total_llm_calls'].astext, Integer),
                    0
                )
            ).label('group_eval_llm_calls'),
            # Average P95 latency from groups
            func.avg(
                func.coalesce(
                    func.cast(AlertGroupDBModel.llm_metrics['p95_latency_sec'].astext, Numeric),
                    0
                )
            ).label('group_avg_p95_latency')
        )
        .select_from(AlertGroupDBModel)
        .outerjoin(
            EvaluationDbModel,
            (EvaluationDbModel.group_id == AlertGroupDBModel.id) & (EvaluationDbModel.status == Status.SUCCESS)
        )
        .where(AlertGroupDBModel.created_at >= start_time)
    )
    if end_time:
        group_query = group_query.where(AlertGroupDBModel.created_at < end_time)

    group_query = group_query.subquery()

    # Combine individual and group metrics
    avg_latency_numerator = (
        func.coalesce(individual_query.c.individual_avg_p95_latency, 0) +
        func.coalesce(group_query.c.group_avg_p95_latency, 0)
    )
    avg_latency_denominator = (
        case((individual_query.c.individual_avg_p95_latency.isnot(None), 1), else_=0) +
        case((group_query.c.group_avg_p95_latency.isnot(None), 1), else_=0)
    )
    combined_query = select(
        # Total cost = individual triages + individual evals + group triages + group evals
        (func.coalesce(individual_query.c.individual_triage_cost, 0) +
         func.coalesce(individual_query.c.individual_eval_cost, 0) +
         func.coalesce(group_query.c.group_triage_cost, 0) +
         func.coalesce(group_query.c.group_eval_cost, 0)).label('total_cost'),
        # Average P95 latency across both individual and group triages
        # Average only across sources that actually have data
        case(
            (avg_latency_denominator > 0, avg_latency_numerator / avg_latency_denominator),
            else_=0
        ).label('avg_p95_latency_sec'),
        # Total LLM calls = individual triages + individual evals + group triages + group evals
        (func.coalesce(individual_query.c.individual_triage_llm_calls, 0) +
         func.coalesce(individual_query.c.individual_eval_llm_calls, 0) +
         func.coalesce(group_query.c.group_triage_llm_calls, 0) +
         func.coalesce(group_query.c.group_eval_llm_calls, 0)).label('total_llm_calls')
    ).select_from(individual_query).join(group_query, literal(True))

    return combined_query


def build_trend_metrics_query(bucket_expr, start_time: datetime, end_time: datetime = None, chaos_enabled: bool = False):
    """
    Build query to get time-series metrics including success rate, audit score, and performance metrics.

    CRITICAL: Handles both grouped and ungrouped alerts correctly:
    - For ungrouped alerts: uses triages table metrics
    - For grouped alerts: uses alert_groups table metrics and status

    Returns: time_bucket, total_count, success_count, avg_audit_score_per_alert, avg_tokens_per_alert, avg_cost_per_alert, avg_processing_time_per_alert
    """
    from src.server.models.db import AlertGroupDBModel

    # Calculate effective triage status (same logic as build_kpi_counts_query)
    # For grouped alerts, map group's triage_status to API Status enum
    # Cast to text to avoid enum type mismatch between alert_groups.triage_status (varchar) and triages.status (enum)
    effective_status = case(
        (
            AlertDbModel.group_id.isnot(None),
            case(
                (AlertGroupDBModel.triage_status == 'completed', literal('success')),
                (AlertGroupDBModel.triage_status == 'in_progress', literal('processing')),
                (AlertGroupDBModel.triage_status == 'failed', literal('error')),
                else_=literal('pending')
            )
        ),
        else_=func.cast(TriageDbModel.status, String)
    ).label('effective_status')

    # Calculate effective metrics (use group metrics for grouped alerts, individual for ungrouped)
    # Use COALESCE to handle NULLs properly in the CASE expression
    effective_tokens = case(
        (AlertDbModel.group_id.isnot(None), AlertGroupDBModel.tokens_used),
        else_=TriageDbModel.tokens_used
    )

    effective_cost = case(
        (AlertDbModel.group_id.isnot(None), AlertGroupDBModel.price_usd),
        else_=TriageDbModel.price_usd
    )

    effective_processing_time = case(
        (AlertDbModel.group_id.isnot(None), AlertGroupDBModel.processing_time_sec),
        else_=TriageDbModel.processing_time_sec
    )

    # Evaluation metrics (evaluations are always per-alert, even for grouped alerts)
    eval_tokens = EvaluationDbModel.tokens_used
    eval_cost = EvaluationDbModel.price_usd
    eval_processing_time = EvaluationDbModel.processing_time_sec

    # Calculate average audit score with proper NULL handling
    # When no evaluation exists (outer join → NULL), treat component scores as NULL
    # The division will only apply to rows that have evaluations
    if chaos_enabled:
        avg_score_expr = func.avg(
            case(
                (EvaluationDbModel.id.isnot(None),
                 (
                    func.coalesce(EvaluationDbModel.root_cause_similarity_percent, 0) +
                    func.coalesce(EvaluationDbModel.orch_agent_util_score_percent, 0) +
                    func.coalesce(EvaluationDbModel.orch_task_completion_score_percent, 0) +
                    func.coalesce(EvaluationDbModel.sub_agent_tool_util_score_percent, 0) +
                    func.coalesce(EvaluationDbModel.sub_agent_task_completion_score, 0)
                 ) / 5.0),
                else_=None  # Return NULL for alerts without evaluations
            )
        )
    else:
        avg_score_expr = func.avg(
            case(
                (EvaluationDbModel.id.isnot(None),
                 (
                    func.coalesce(EvaluationDbModel.orch_agent_util_score_percent, 0) +
                    func.coalesce(EvaluationDbModel.orch_task_completion_score_percent, 0) +
                    func.coalesce(EvaluationDbModel.sub_agent_tool_util_score_percent, 0) +
                    func.coalesce(EvaluationDbModel.sub_agent_task_completion_score, 0)
                 ) / 4.0),
                else_=None  # Return NULL for alerts without evaluations
            )
        )

    query = select(
        # Time bucket
        bucket_expr.label('time_bucket'),
        # Total alerts in the time bucket
        func.count(func.distinct(AlertDbModel.id)).label('total_count'),
        # Successfully triaged alert count - uses effective status to handle groups correctly
        func.sum(case((effective_status != 'error', 1), else_=0)).label('success_count'),
        # Average audit score per alert in the time bucket
        avg_score_expr.label('avg_audit_score_per_alert'),
        # Average tokens per alert - uses effective metrics (group or individual)
        # Use COALESCE to handle NULL values from outer joins
        func.avg(
            func.coalesce(effective_tokens, 0) +
            func.coalesce(eval_tokens, 0)
        ).label('avg_tokens_per_alert'),
        # Average cost per alert - uses effective metrics (group or individual)
        func.avg(
            func.coalesce(effective_cost, 0) +
            func.coalesce(eval_cost, 0)
        ).label('avg_cost_per_alert'),
        # Average processing time per alert - uses effective metrics (group or individual)
        func.avg(
            func.coalesce(effective_processing_time, 0) +
            func.coalesce(eval_processing_time, 0)
        ).label('avg_processing_time_per_alert')
    ).select_from(AlertDbModel).join(
        TriageDbModel,
        TriageDbModel.alert_id == AlertDbModel.id
    ).outerjoin(
        AlertGroupDBModel,
        AlertGroupDBModel.id == AlertDbModel.group_id
    ).outerjoin(
        EvaluationDbModel,
        (EvaluationDbModel.alert_id == AlertDbModel.id) & (EvaluationDbModel.status == Status.SUCCESS)
    )

    # Updated where clause to support end_time
    if end_time:
        query = query.where(
            (AlertDbModel.created_at >= start_time) & (AlertDbModel.created_at < end_time)
        )
    else:
        query = query.where(AlertDbModel.created_at >= start_time)

    return query.group_by(bucket_expr).order_by(bucket_expr)


def build_kpi_cards(
        current_counts_result,
        current_metrics_result
) -> Tuple[List[KpiMetric], Dict]:
    """
    Process KPI query results and return KPI metrics.

    Returns:
        Tuple of (kpi_metrics, triage_data_dict)
    """
    rows = current_counts_result.all()
    triage_data = {row[0]: row[1] for row in rows}
    total_alerts = sum(triage_data.values())

    if total_alerts == 0:
        return [], {}

    metrics_row = current_metrics_result.first()

    total_cost = float(metrics_row.total_cost) if metrics_row and metrics_row.total_cost else 0

    avg_p95_latency_sec = float(metrics_row.avg_p95_latency_sec) \
        if metrics_row and metrics_row.avg_p95_latency_sec else 0

    total_llm_calls = int(metrics_row.total_llm_calls) if metrics_row and metrics_row.total_llm_calls else 0

    kpi_metrics = [
        KpiMetric(
            label="Total Alerts",
            value=f"{total_alerts:,}",
            tooltip="Total number of alerts in selected time range"
        ),
        KpiMetric(
            label="Total Cost",
            value=f"${total_cost:.4f}",
            tooltip="Total cost in USD for selected time range"
        ),
        KpiMetric(
            label="Total LLM Calls",
            value=f"{total_llm_calls:,}",
            tooltip="Total number of LLM calls across all alerts in selected time range"
        ),
        KpiMetric(
            label="Avg P95 Latency",
            value=f"{avg_p95_latency_sec:.2f}s",
            tooltip="Average P95 latency across all alerts in selected time range"
        )
    ]

    return kpi_metrics, triage_data


def build_status_distribution(triage_data: Dict, color_map: Dict) -> List[StatusDistributionItem]:
    """
    Build status distribution pie chart data from triage data.
    Combines PENDING, QUEUED, and NULL statuses and displays them as "pending".

    Returns:
        List of StatusDistributionItem
    """
    status_colors = {
        Status.SUCCESS: color_map["green"],
        Status.ERROR: color_map["red"],
        Status.PENDING: color_map["orange"],
        Status.PROCESSING: color_map["blue"]
    }

    # Combine PENDING, QUEUED, and NULL (never triaged) into a single "pending" status
    combined_data = {}
    for status, count in triage_data.items():
        # Normalize status to lowercase string (database might return uppercase)
        if isinstance(status, str):
            status_str = status.lower()
        elif status is None:
            status_str = 'pending'
        else:
            status_str = status.value if hasattr(status, 'value') else str(status).lower()

        # Map NULL (no triage), PENDING, and QUEUED to PENDING for display
        if status_str in (None, 'pending', 'queued'):
            display_status = 'pending'
        else:
            display_status = status_str

        combined_data[display_status] = combined_data.get(display_status, 0) + count

    total_triages = sum(combined_data.values())
    return [
        StatusDistributionItem(
            name=status,
            value=int(count / total_triages * 100) if total_triages > 0 else 0,
            count=count,
            color=status_colors.get(Status(status) if status in ['pending', 'queued', 'processing', 'success', 'error'] else Status.PENDING, color_map["grey"])
        )
        for status, count in combined_data.items()
    ]


def calculate_average(data_points: List[TimeSeriesDataPoint]) -> float:
    """
    Calculate average value from data points.

    Returns:
        Average value as float
    """
    active_values = [point.value for point in data_points if point.value > 0]
    if not active_values:
        return 0.0
    return sum(active_values) / len(active_values)


def get_bucket_config(time_delta: timedelta) -> tuple[int, int, str]:
    """
    Calculate bucket configuration based on time duration.

    Returns: (bucket_minutes, total_buckets, date_trunc_unit)
    """
    total_seconds = time_delta.total_seconds()
    total_minutes = total_seconds / 60
    total_hours = total_minutes / 60
    total_days = total_hours / 24

    if total_hours <= 1:
        bucket_minutes = 5
        total_buckets = max(1, int(total_minutes / bucket_minutes))
        trunc_unit = 'minute'
    elif total_hours <= 6:
        bucket_minutes = 30
        total_buckets = max(1, int(total_minutes / bucket_minutes))
        trunc_unit = 'minute'
    elif total_hours <= 24:
        bucket_minutes = 60
        total_buckets = max(1, int(total_hours))
        trunc_unit = 'hour'
    elif total_days <= 7:
        bucket_minutes = 1440  # 1 day in minutes
        total_buckets = max(1, int(total_days))
        trunc_unit = 'day'
    else:
        bucket_minutes = 1440
        total_buckets = min(max(1, int(total_days)), 30)  # Cap at 30 buckets
        trunc_unit = 'day'

    return bucket_minutes, total_buckets, trunc_unit


def build_trend_charts(
        time_series_result,
        time_range: Timeline,
        time_delta_map: Dict,
        end_time: datetime,  # Changed from 'now' to 'end_time'
        color_map: Dict
) -> List[PlotConfig]:
    """
    Build all trend chart configurations from time series data.

    Returns:
        List of PlotConfig for all charts
    """
    # Get time_delta for the given time_range
    if time_range == Timeline.CUSTOM:
        time_delta = time_delta_map[Timeline.CUSTOM]
    else:
        time_delta = time_delta_map[time_range]

    # Use get_bucket_config for all time ranges (eliminates code duplication)
    bucket_minutes, total_buckets, _ = get_bucket_config(time_delta)

    time_series_rows = time_series_result.all()
    audit_scores_per_alert_by_time = {}
    success_percentage_by_time = {}
    tokens_per_alert_by_time = {}
    cost_per_alert_by_time = {}
    processing_time_per_alert_by_time = {}

    for row in time_series_rows:
        time_bucket = row.time_bucket
        total_count = row.total_count or 0
        success_count = row.success_count or 0
        success_percentage = (success_count / total_count * 100) if total_count > 0 else 0
        success_percentage_by_time[time_bucket] = success_percentage
        audit_scores_per_alert_by_time[time_bucket] = row.avg_audit_score_per_alert or 0
        tokens_per_alert_by_time[time_bucket] = row.avg_tokens_per_alert or 0
        cost_per_alert_by_time[time_bucket] = row.avg_cost_per_alert or 0
        processing_time_per_alert_by_time[time_bucket] = row.avg_processing_time_per_alert or 0

    audit_score_per_alert_data = []
    success_triage_data = []
    avg_tokens_per_alert_data = []
    avg_cost_per_alert_data = []
    avg_processing_time_per_alert_data = []

    for i in reversed(range(total_buckets)):
        # Updated bucket iteration - use end_time instead of now
        if bucket_minutes >= 1440:  # Day-level buckets
            bucket_time = (end_time - timedelta(days=i + 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            bucket_time = (end_time - timedelta(minutes=(i + 1) * bucket_minutes)).replace(second=0, microsecond=0)
            if bucket_minutes >= 60:
                bucket_time = bucket_time.replace(minute=0)

        audit_score_per_alert_value = audit_scores_per_alert_by_time.get(bucket_time, 0)
        audit_score_per_alert_data.append(TimeSeriesDataPoint(
            timestamp=int(bucket_time.timestamp() * 1000),
            value=round(audit_score_per_alert_value, 2)
        ))

        success_percentage = success_percentage_by_time.get(bucket_time, 0)
        success_triage_data.append(TimeSeriesDataPoint(
            timestamp=int(bucket_time.timestamp() * 1000),
            value=round(success_percentage, 2)
        ))

        tokens_per_alert_value = tokens_per_alert_by_time.get(bucket_time, 0)
        avg_tokens_per_alert_data.append(TimeSeriesDataPoint(
            timestamp=int(bucket_time.timestamp() * 1000),
            value=round(float(tokens_per_alert_value) / 1000.0, 2)
        ))

        avg_cost_per_alert_data.append(TimeSeriesDataPoint(
            timestamp=int(bucket_time.timestamp() * 1000),
            value=round(cost_per_alert_by_time.get(bucket_time, 0), 4)
        ))

        avg_processing_time_per_alert_data.append(TimeSeriesDataPoint(
            timestamp=int(bucket_time.timestamp() * 1000),
            value=round(processing_time_per_alert_by_time.get(bucket_time, 0), 2)
        ))

    success_rate_avg = calculate_average(success_triage_data)
    audit_score_avg = calculate_average(audit_score_per_alert_data)
    processing_time_avg = calculate_average(avg_processing_time_per_alert_data)
    tokens_avg = calculate_average(avg_tokens_per_alert_data)
    cost_avg = calculate_average(avg_cost_per_alert_data)

    return [
        # Quality Trends
        PlotConfig(
            title="Triage Success Rate",
            plot_details=LineChartDetail(
                data_points=success_triage_data,
                color=color_map["green"],
                show_dots=True,
                average=f"{success_rate_avg:.1f}%"
            ),
            tooltip="Percentage of successful triages over time"
        ),
        PlotConfig(
            title="Avg Audit Score %",
            plot_details=LineChartDetail(
                data_points=audit_score_per_alert_data,
                color=color_map["blue"],
                show_dots=True,
                average=f"{audit_score_avg:.1f}%"
            ),
            tooltip="Average evaluation score percentage per alert over time"
        ),
        # Performance Trend
        PlotConfig(
            title="Avg Processing Time",
            plot_details=LineChartDetail(
                data_points=avg_processing_time_per_alert_data,
                color=color_map["blue"],
                show_dots=True,
                average=f"{processing_time_avg:.1f}s"
            ),
            tooltip="Average processing time in seconds per alert over time"
        ),
        # Resource Trend
        PlotConfig(
            title="Avg Token Usage (k)",
            plot_details=LineChartDetail(
                data_points=avg_tokens_per_alert_data,
                color=color_map["blue"],
                show_dots=True,
                average=f"{tokens_avg:.2f}k"
            ),
            tooltip="Average number of tokens used per alert (in thousands)"
        ),
        # Cost Trend
        PlotConfig(
            title="Avg Cost per Alert",
            plot_details=LineChartDetail(
                data_points=avg_cost_per_alert_data,
                color=color_map["orange"],
                show_dots=True,
                average=f"${cost_avg:.4f}"
            ),
            tooltip="Average cost in USD per alert over time"
        )
    ]


@router.get("/summary")
async def get_overview_stats(
        request: OverviewStatsRequest = Depends(),
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> OverviewStatsResponse:
    """
    Get overview statistics including KPI metrics, status distribution, and trend charts.
    """
    # Validate custom time range parameters
    is_valid, error_msg = validate_custom_time_range(request.time_range, request.start_time, request.end_time)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    now = datetime.now(timezone.utc)
    time_delta_map = {
        Timeline.THIRTY_MINS: timedelta(minutes=30),
        Timeline.ONE_HOUR: timedelta(hours=1),
        Timeline.SIX_HOURS: timedelta(hours=6),
        Timeline.TWENTY_FOUR_HOURS: timedelta(hours=24),
        Timeline.SEVEN_DAYS: timedelta(days=7),
        Timeline.THIRTY_DAYS: timedelta(days=30)
    }

    color_map = {
        "red": "#ef4444",
        "orange": "#f59e0b",
        "green": "#22c55e",
        "blue": "#3b82f6",
        "grey": "#6b7280",
    }

    # Calculate start_time, end_time, and time_delta based on time_range
    if request.time_range == Timeline.CUSTOM:
        start_time = request.start_time
        end_time = request.end_time
        time_delta = end_time - start_time
    else:
        time_delta = time_delta_map[request.time_range]
        end_time = now
        start_time = now - time_delta

    chaos_enabled = await is_chaos_system_enabled()

    # Get bucket configuration for custom ranges
    if request.time_range == Timeline.CUSTOM:
        _, _, trunc_unit = get_bucket_config(time_delta)  # Only trunc_unit needed here
        bucket_expr = func.date_trunc(trunc_unit, AlertDbModel.created_at)
    else:
        # Existing logic for predefined ranges
        if request.time_range in [Timeline.THIRTY_MINS, Timeline.ONE_HOUR]:
            bucket_expr = func.date_trunc('minute', AlertDbModel.created_at)
        elif request.time_range == Timeline.SIX_HOURS:
            bucket_expr = func.date_trunc('minute', AlertDbModel.created_at)
        elif request.time_range == Timeline.TWENTY_FOUR_HOURS:
            bucket_expr = func.date_trunc('hour', AlertDbModel.created_at)
        else:
            bucket_expr = func.date_trunc('day', AlertDbModel.created_at)

    # Update query calls to pass end_time for custom ranges
    current_counts_query = build_kpi_counts_query(start_time, end_time if request.time_range == Timeline.CUSTOM else None)
    current_metrics_query = build_kpi_metrics_query(start_time, end_time if request.time_range == Timeline.CUSTOM else None)
    trend_query = build_trend_metrics_query(bucket_expr, start_time, end_time if request.time_range == Timeline.CUSTOM else None, chaos_enabled=chaos_enabled)

    # Execute queries sequentially to avoid SQLAlchemy concurrency issues
    # (same session cannot handle concurrent operations)
    current_counts_result = await session.execute(current_counts_query)
    current_metrics_result = await session.execute(current_metrics_query)
    trend_result = await session.execute(trend_query)

    kpi_metrics, triage_data = build_kpi_cards(
        current_counts_result,
        current_metrics_result
    )

    if not kpi_metrics and not triage_data:
        return OverviewStatsResponse(
            kpi_metrics=[],
            plots=[]
        )

    status_distribution = build_status_distribution(triage_data, color_map)
    # Update build_trend_charts call to use end_time and handle custom ranges
    trend_charts = build_trend_charts(
        trend_result,
        request.time_range,
        time_delta_map if request.time_range != Timeline.CUSTOM else {Timeline.CUSTOM: time_delta},
        end_time,  # Use end_time instead of now
        color_map
    )

    status_pie_chart = PlotConfig(
        title="Triage Status Distribution",
        plot_details=PieChartDetail(data=status_distribution),
        tooltip="Distribution of triage statuses"
    )

    all_plots = [status_pie_chart] + trend_charts

    return OverviewStatsResponse(
        kpi_metrics=kpi_metrics,
        plots=all_plots
    )

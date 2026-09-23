"""
Alert Groups API endpoints.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.server.apis_v1.dependencies import get_current_user, get_db_session
from src.server.apis_v1.helpers import (
    get_formatted_triage_analysis_messages,
    format_group_root_cause_analysis_content,
    get_latest_group_evaluation_record,
)
from src.server.models.api.alert_group_list import (
    AlertGroupListRequest,
    AlertGroupListItem,
    AlertGroupListResponse,
)
from src.server.models.api.alert_group_details import (
    AlertGroupDetailResponse,
    AlertInGroup,
)
from src.server.models.api.alert_traige import TriageJourneyResponse
from src.server.models.api.alert_root_cause import TriageRCAResponse
from src.server.models.api.alert_triage_evaluation import (
    TriageEvaluationResponse,
    ScoreCriteriaCard,
)
from src.server.models.api.enums import Severity, Status
from src.server.models.api.jobs import JobStatusResponse
from src.server.models.api.pagination_meta import PaginationMeta
from src.server.models.api.add_alerts_to_group import AddAlertsToGroupRequest, AddAlertsToGroupResponse
from src.server.models.api.remove_alerts_from_group import RemoveAlertsFromGroupRequest, RemoveAlertsFromGroupResponse
from src.server.models.db import AlertGroupDBModel, AlertDBModel, EvaluationDBModel
from src.server.utilities import get_queue

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_alert_groups(
    request: AlertGroupListRequest = Depends(),
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AlertGroupListResponse:
    """
    List alert groups with filtering and pagination.
    """
    try:
        # Build base query
        query = select(AlertGroupDBModel)

        # Apply filters
        filters = []

        if request.severity:
            filters.append(AlertGroupDBModel.severity == request.severity)

        if request.triage_status:
            # Map Status enum to triage_status string
            status_map = {
                Status.PENDING: "pending",
                Status.PROCESSING: "in_progress",
                Status.SUCCESS: "completed",
                Status.ERROR: "failed",
            }
            triage_status_str = status_map.get(
                request.triage_status, request.triage_status.value
            )
            filters.append(AlertGroupDBModel.triage_status == triage_status_str)

        if request.status:
            filters.append(AlertGroupDBModel.status == request.status)

        if request.name_contains:
            filters.append(
                AlertGroupDBModel.group_name.ilike(f"%{request.name_contains}%")
            )

        # Time range filtering
        if request.time_range:
            from datetime import datetime, timedelta, timezone

            if request.time_range == "custom":
                # Use custom start_time and end_time
                if request.start_time and request.end_time:
                    filters.append(AlertGroupDBModel.created_at >= request.start_time)
                    filters.append(AlertGroupDBModel.created_at <= request.end_time)
            else:
                # Use predefined time range
                now = datetime.now(timezone.utc)
                time_delta_map = {
                    "30m": timedelta(minutes=30),
                    "1h": timedelta(hours=1),
                    "6h": timedelta(hours=6),
                    "24h": timedelta(hours=24),
                    "7d": timedelta(days=7),
                    "30d": timedelta(days=30),
                }

                if request.time_range in time_delta_map:
                    start_time = now - time_delta_map[request.time_range]
                    filters.append(AlertGroupDBModel.created_at >= start_time)

        # Evaluation status filtering
        if request.evaluation_status:
            filters.append(
                AlertGroupDBModel.evaluations.any(
                    EvaluationDBModel.status == request.evaluation_status
                )
            )

        # Score filtering
        if (request.evaluation_score_operator is not None and
            request.evaluation_score_value is not None):
            from sqlalchemy import case

            score_value = request.evaluation_score_value

            # Calculate average score using SQLAlchemy functions
            # Count non-null score fields
            non_null_count = (
                case((EvaluationDBModel.root_cause_similarity_percent.is_not(None), 1), else_=0) +
                case((EvaluationDBModel.orch_agent_util_score_percent.is_not(None), 1), else_=0) +
                case((EvaluationDBModel.orch_task_completion_score_percent.is_not(None), 1), else_=0) +
                case((EvaluationDBModel.sub_agent_tool_util_score_percent.is_not(None), 1), else_=0) +
                case((EvaluationDBModel.sub_agent_task_completion_score.is_not(None), 1), else_=0)
            )

            # Sum non-null score fields
            score_sum = (
                func.coalesce(EvaluationDBModel.root_cause_similarity_percent, 0) +
                func.coalesce(EvaluationDBModel.orch_agent_util_score_percent, 0) +
                func.coalesce(EvaluationDBModel.orch_task_completion_score_percent, 0) +
                func.coalesce(EvaluationDBModel.sub_agent_tool_util_score_percent, 0) +
                func.coalesce(EvaluationDBModel.sub_agent_task_completion_score, 0)
            )

            # Calculate average score
            avg_score = case(
                (non_null_count > 0, score_sum / func.nullif(non_null_count, 0)),
                else_=None
            )

            # Apply the operator using SQLAlchemy comparison
            if request.evaluation_score_operator == ">":
                score_comparison = avg_score > score_value
            elif request.evaluation_score_operator == "<":
                score_comparison = avg_score < score_value
            elif request.evaluation_score_operator == ">=":
                score_comparison = avg_score >= score_value
            elif request.evaluation_score_operator == "<=":
                score_comparison = avg_score <= score_value
            else:
                score_comparison = None

            if score_comparison is not None:
                # Filter groups that have evaluations matching the score condition
                filters.append(
                    AlertGroupDBModel.evaluations.any(
                        and_(
                            EvaluationDBModel.status == Status.SUCCESS,
                            score_comparison
                        )
                    )
                )

        if filters:
            query = query.where(and_(*filters))

        # Order by created_at descending (newest first)
        query = query.order_by(AlertGroupDBModel.created_at.desc())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total_count = total_result.scalar() or 0

        # Apply pagination
        offset = (request.page - 1) * request.page_size
        query = query.offset(offset).limit(request.page_size)

        # Execute query with eager loading of alerts for count
        query = query.options(selectinload(AlertGroupDBModel.alerts))
        result = await session.execute(query)
        groups = result.scalars().all()

        # Convert to response models
        group_items = []
        for group in groups:
            # Calculate alert count from relationship
            alert_count = len(group.alerts) if group.alerts else 0

            # Get latest evaluation score if available
            # Use a subquery to fetch the latest evaluation for this group
            evaluation_score = None
            eval_query = (
                select(EvaluationDBModel)
                .where(EvaluationDBModel.group_id == group.id)
                .order_by(EvaluationDBModel.created_at.desc())
                .limit(1)
            )
            eval_result = await session.execute(eval_query)
            latest_evaluation = eval_result.scalar_one_or_none()

            if latest_evaluation:
                # Calculate average score from individual score fields
                scores = []
                if latest_evaluation.root_cause_similarity_percent is not None:
                    scores.append(latest_evaluation.root_cause_similarity_percent)
                if latest_evaluation.orch_agent_util_score_percent is not None:
                    scores.append(latest_evaluation.orch_agent_util_score_percent)
                if latest_evaluation.orch_task_completion_score_percent is not None:
                    scores.append(latest_evaluation.orch_task_completion_score_percent)
                if latest_evaluation.sub_agent_tool_util_score_percent is not None:
                    scores.append(latest_evaluation.sub_agent_tool_util_score_percent)
                if latest_evaluation.sub_agent_task_completion_score is not None:
                    scores.append(latest_evaluation.sub_agent_task_completion_score)

                if scores:
                    evaluation_score = round(sum(scores) / len(scores), 1)

            group_items.append(
                AlertGroupListItem(
                    id=str(group.id),
                    group_name=group.group_name,
                    alert_count=alert_count,
                    severity=group.severity,
                    triage_status=group.triage_status,
                    status=group.status,
                    evaluation_score=evaluation_score,
                    created_at=group.created_at,
                    updated_at=group.updated_at,
                    triaged_at=group.triaged_at,
                )
            )

        # Calculate pagination metadata
        total_pages = (total_count + request.page_size - 1) // request.page_size

        pagination = PaginationMeta(
            current_page=request.page,
            page_size=request.page_size,
            total_items=total_count,
            total_pages=total_pages,
        )

        return AlertGroupListResponse(groups=group_items, pagination=pagination)

    except Exception:
        logger.exception("Failed to list alert groups")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert groups",
        )


@router.get("/{id}")
async def get_alert_group(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AlertGroupDetailResponse:
    """
    Get detailed information about a specific alert group.
    """
    try:
        # Fetch group with alerts
        stmt = (
            select(AlertGroupDBModel)
            .where(AlertGroupDBModel.id == int(id))
            .options(selectinload(AlertGroupDBModel.alerts))
        )
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group with ID '{id}' not found",
            )

        # Convert alerts to response model
        alerts_in_group = []
        for alert in group.alerts:
            # Extract labels and annotations from payload
            payload = alert.payload or {}
            labels = payload.get("labels", {})
            annotations = payload.get("annotations", {})

            alerts_in_group.append(
                AlertInGroup(
                    id=str(alert.id),
                    alert_name=alert.alert_name or "Unknown",
                    severity=alert.severity or Severity.P3,
                    alert_status=alert.alert_status or "firing",
                    created_at=alert.created_at,
                    alert_source=alert.alert_source or "unknown",
                    labels=labels,
                    annotations=annotations,
                )
            )

        # Calculate alert count
        alert_count = len(alerts_in_group)

        return AlertGroupDetailResponse(
            id=str(group.id),
            group_name=group.group_name,
            alert_count=alert_count,
            severity=group.severity,
            triage_status=group.triage_status,
            status=group.status,
            root_cause_summary=group.root_cause_summary,
            created_at=group.created_at,
            updated_at=group.updated_at,
            triaged_at=group.triaged_at,
            tokens_used=group.tokens_used,
            price_usd=float(group.price_usd) if group.price_usd else None,
            processing_time_sec=group.processing_time_sec,
            grouping_confidence=(
                float(group.grouping_confidence) if group.grouping_confidence else None
            ),
            grouping_reasoning=group.grouping_reasoning,
            alerts=alerts_in_group,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to get alert group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert group",
        )


@router.get("/{id}/root-cause")
async def get_alert_group_root_cause(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TriageRCAResponse:
    """
    Get root cause analysis for an alert group.

    Args:
        id: Alert group identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Root cause analysis information in markdown format

    Raises:
        HTTPException: 404 if alert group not found, 500 for server errors
    """
    try:
        logger.info(
            f"Getting root cause analysis for alert group {id}, user: {current_user}"
        )

        # Fetch alert group
        stmt = select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group with ID '{id}' not found",
            )

        # Use the same helper function as the alert RCA endpoint
        # Pass for_individual_alert=False since this is the group RCA endpoint
        content = format_group_root_cause_analysis_content(
            group, for_individual_alert=False
        )
        return TriageRCAResponse(content=content)

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to get root cause for alert group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve root cause analysis",
        )


@router.get("/{id}/triage")
async def get_alert_group_triage_journey(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TriageJourneyResponse:
    """
    Get the complete triage journey for an alert group.

    This endpoint retrieves the step-by-step triage analysis journey from the checkpoint database,
    showing all LLM interactions, tool calls, and agent reasoning that led to the final RCA.
    """
    try:
        # Fetch alert group
        stmt = select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group with ID '{id}' not found",
            )

        # Check if triage has been performed
        if not group.thread_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No triage journey found for alert group '{id}'. Triage may not have been performed yet.",
            )

        # Fetch triage journey from checkpoint database using thread_id
        # Reuse the same helper function used for individual alerts
        messages = await get_formatted_triage_analysis_messages(group.thread_id)

        if not messages:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Triage journey data not found in checkpoint database for alert group '{id}'",
            )

        return TriageJourneyResponse(
            alert_id=id,  # Using group ID as alert_id for consistency with response model
            messages=messages,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to get triage journey for alert group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve triage journey",
        )


@router.post("/{id}/triage", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_group_triage(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobStatusResponse:
    """
    Trigger manual triage analysis for a specific alert group.

    Args:
        id: Alert group identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Triage job information

    Raises:
        HTTPException: 404 if group not found, 409 if triage already in progress, 500 for server errors
    """
    try:
        logger.info(
            f"Triggering manual triage for alert group {id}, user: {current_user}"
        )

        # Fetch alert group
        stmt = select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group with ID '{id}' not found",
            )

        # Check if triage is already in progress or queued
        if group.triage_status == "in_progress":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Triage is already in progress for alert group '{id}'. Please wait for it to complete.",
            )
        if group.triage_status == "queued":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Triage is already queued for alert group '{id}'. Please wait for it to start.",
            )

        # Generate new thread_id for LangGraph checkpointing
        thread_id = str(uuid.uuid4())

        # Update group status to QUEUED (not in_progress yet)
        # Worker will update to in_progress when it picks up the job
        group.triage_status = "queued"
        group.thread_id = thread_id
        group.root_cause_summary = None  # Clear previous results
        group.error_message = None
        group.triaged_at = None
        group.tokens_used = None
        group.price_usd = None
        group.processing_time_sec = None
        group.llm_metrics = None
        await session.commit()

        # Get the alert_grouping queue
        queue = get_queue("alert_grouping")

        # Import the worker function
        from src.server.async_workers.group_triage_job import execute_group_triage_job

        # Enqueue the triage job (no timeout - let it run as long as needed)
        job = queue.enqueue(
            execute_group_triage_job,
            group_id=group.id,
            thread_id=thread_id,
            job_timeout=-1,  # No timeout for long-running LangGraph execution
        )

        # Store job_id in the group record
        group.job_id = job.id
        await session.commit()

        logger.info(
            f"Manual group triage job enqueued: job_id={job.id}, thread_id={thread_id}, group_id={id}"
        )

        return JobStatusResponse(job_id=job.id, status="queued")

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to trigger triage for alert group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger triage analysis",
        )


@router.get("/{id}/evaluation")
async def get_alert_group_evaluation(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TriageEvaluationResponse:
    """
    Get evaluation details for an alert group.

    Args:
        id: Alert group identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Evaluation details with score cards for non-null scores only

    Raises:
        HTTPException: 404 if group not found, 500 for server errors
    """
    try:
        logger.info(
            f"Getting evaluation details for alert group {id}, user: {current_user}"
        )

        # Get group from database
        group = await session.scalar(
            select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group {id} not found",
            )

        # Get the latest evaluation record for this group
        latest_evaluation = await get_latest_group_evaluation_record(group.id, session)  # type: ignore

        if latest_evaluation is None:
            # No evaluation exists yet
            return TriageEvaluationResponse(
                average_score_percent=0.0,
                reason="No evaluation has been performed for this alert group yet.",
                score_criteria_cards=[],
                status=None,
            )

        if latest_evaluation.status != Status.SUCCESS:
            # Evaluation exists but not successful
            status_messages = {
                Status.PENDING: "Evaluation is currently pending.",
                Status.QUEUED: "Evaluation has been queued and will start processing soon.",
                Status.PROCESSING: "Evaluation is currently in progress.",
                Status.ERROR: "Evaluation failed with an error.",
            }
            return TriageEvaluationResponse(
                average_score_percent=0.0,
                reason=status_messages.get(
                    latest_evaluation.status, "Evaluation is not yet complete."
                ),
                score_criteria_cards=[],
                status=latest_evaluation.status.value if latest_evaluation.status else None,
            )

        # Build score criteria cards for non-null scores only
        score_criteria_cards = []

        # Define score mappings with titles and descriptions
        score_mappings = [
            {
                "value": latest_evaluation.root_cause_similarity_percent,
                "title": "Root Cause Similarity",
                "description": "Measures the accuracy of AI-generated root cause analysis against expected outcomes.",
            },
            {
                "value": latest_evaluation.orch_agent_util_score_percent,
                "title": "Orchestrator Agent Utilization",
                "description": "Evaluates the orchestrator's effectiveness in coordinating specialized agents and "
                "leveraging knowledge base resources.",
            },
            {
                "value": latest_evaluation.orch_task_completion_score_percent,
                "title": "Orchestrator Task Completion",
                "description": "Assesses the orchestrator's performance in completing the comprehensive "
                "group triage workflow.",
            },
            {
                "value": latest_evaluation.sub_agent_tool_util_score_percent,
                "title": "Sub-Agent Tool Utilization",
                "description": "Evaluates specialized agents' proficiency in utilizing assigned tools and "
                "resources for their specific tasks.",
            },
            {
                "value": latest_evaluation.sub_agent_task_completion_score,
                "title": "Sub-Agent Task Completion",
                "description": "Measures the effectiveness of specialized agents in executing their designated "
                "responsibilities within the triage process.",
            },
        ]

        # Create cards only for non-null scores
        valid_scores = []
        for score_info in score_mappings:
            if score_info["value"] is not None:
                score_criteria_cards.append(
                    ScoreCriteriaCard(
                        title=score_info["title"],
                        score_percent=score_info["value"],
                        description=score_info["description"],
                    )
                )
                valid_scores.append(score_info["value"])

        # Calculate average score from non-null scores
        if valid_scores:
            average_score = round(sum(valid_scores) / len(valid_scores), 0)
            reason = latest_evaluation.reason or "Evaluation completed successfully."
        else:
            average_score = 0
            reason = "No valid evaluation scores available."

        return TriageEvaluationResponse(
            average_score_percent=average_score,
            reason=reason,
            score_criteria_cards=score_criteria_cards,
            status="success",
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to get evaluation details for alert group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve evaluation details",
        )


@router.post("/{id}/evaluation", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_group_evaluation(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JobStatusResponse:
    """
    Trigger manual evaluation for an alert group.

    Creates an evaluation record and enqueues an evaluation job.

    Args:
        id: Alert group identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Job status response with job_id

    Raises:
        HTTPException: 404 if group not found, 400 if triage not complete, 500 for server errors
    """
    try:
        logger.info(
            f"Triggering manual evaluation for alert group {id}, user: {current_user}"
        )

        # Get group from database
        group = await session.scalar(
            select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group {id} not found",
            )

        # Check if triage is complete
        if group.triage_status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot evaluate group {id}: triage status is '{group.triage_status}', must be 'completed'",
            )

        # Check if evaluation already exists
        existing_eval = await get_latest_group_evaluation_record(group.id, session)  # type: ignore

        if existing_eval:
            # Update existing evaluation record
            eval_record = existing_eval
            eval_record.status = Status.QUEUED
            eval_record.error_message = None
        else:
            # Create new evaluation record
            eval_record = EvaluationDBModel(
                group_id=group.id,
                alert_id=None,  # Explicitly set to None for group evaluation
                status=Status.QUEUED,
            )
            session.add(eval_record)

        await session.commit()
        await session.refresh(eval_record)

        # Enqueue evaluation job
        queue = get_queue("group_evaluations")

        # Import here to avoid circular dependency
        from src.triage_evaluation.group_evaluation_job import (
            execute_group_evaluation_job,
        )

        job = queue.enqueue(
            execute_group_evaluation_job, group_id=group.id, job_timeout="30m"
        )

        # Update evaluation record with job_id
        eval_record.job_id = job.id
        await session.commit()

        logger.info(
            f"Manual group evaluation job enqueued: job_id={job.id}, group_id={id}"
        )

        return JobStatusResponse(job_id=job.id, status="queued")

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to trigger evaluation for alert group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger evaluation",
        )


@router.post("/{id}/alerts", status_code=status.HTTP_200_OK)
async def add_alerts_to_group(
    id: str,
    request: AddAlertsToGroupRequest,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> AddAlertsToGroupResponse:
    """
    Add ungrouped alerts to an existing alert group.

    This endpoint allows users to add more ungrouped alerts to an existing group.
    Only alerts that are not already in a group can be added.

    Args:
        id: Alert group ID
        request: List of alert IDs to add
        current_user: Authenticated user
        session: Database session

    Returns:
        Updated group information

    Raises:
        HTTPException: 404 if group not found, 400 if alerts don't exist or are already grouped
    """
    try:
        logger.info(
            f"Adding {len(request.alert_ids)} alerts to group {id}, user: {current_user}"
        )

        # Get the group
        group = await session.scalar(
            select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group {id} not found"
            )

        # Check if group is being triaged
        if group.triage_status == "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify group while triage is in progress"
            )

        # Validate all alerts exist and are ungrouped
        alert_int_ids = [int(aid) for aid in request.alert_ids]

        alerts_query = (
            select(AlertDBModel)
            .where(AlertDBModel.id.in_(alert_int_ids))
            .options(selectinload(AlertDBModel.triage_sessions))
        )
        result = await session.execute(alerts_query)
        alerts = result.scalars().all()

        if len(alerts) != len(alert_int_ids):
            found_ids = {a.id for a in alerts}
            missing_ids = set(alert_int_ids) - found_ids
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Alerts not found: {missing_ids}"
            )

        # Check if any alerts are already grouped
        already_grouped = [str(a.id) for a in alerts if a.group_id is not None]
        if already_grouped:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Some alerts are already in a group: {already_grouped}"
            )

        # Check if the target group has already been triaged successfully
        if group.triage_status == "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add alerts to group '{group.group_name}' because it has already been triaged successfully. "
                       f"Adding new alerts would invalidate the existing triage analysis."
            )

        # Check if any alerts have already been triaged (individually OR as part of another group)
        already_triaged = []
        for alert in alerts:
            if alert.triage_sessions:
                # Check if any triage session has completed successfully
                for triage in alert.triage_sessions:
                    if triage.status == Status.SUCCESS and triage.root_cause_summary:
                        already_triaged.append(str(alert.id))
                        break

        if already_triaged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add alerts {already_triaged} to group because they have already been triaged. "
                       f"Adding already-triaged alerts would lose their existing triage analysis."
            )

        # Add all alerts to the group
        for alert in alerts:
            alert.group_id = group.id

        # Update group severity if any new alert has higher severity
        severities_order = {Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        new_highest_severity = min(alerts, key=lambda a: severities_order.get(a.severity, 3)).severity
        current_severity_priority = severities_order.get(group.severity, 3)
        new_severity_priority = severities_order.get(new_highest_severity, 3)

        if new_severity_priority < current_severity_priority:
            group.severity = new_highest_severity

        await session.commit()

        # Get total alert count
        total_alerts_result = await session.execute(
            select(func.count(AlertDBModel.id)).where(AlertDBModel.group_id == group.id)
        )
        total_alerts = total_alerts_result.scalar() or 0

        logger.info(
            f"Added {len(alerts)} alerts to group {id}. Total alerts: {total_alerts}"
        )

        return AddAlertsToGroupResponse(
            group_id=group.id,
            group_name=group.group_name,
            alerts_added=len(alerts),
            total_alerts=total_alerts,
            message=f"Successfully added {len(alerts)} alerts to group '{group.group_name}'"
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to add alerts to group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add alerts to group"
        )


@router.delete("/{id}/alerts", status_code=status.HTTP_200_OK)
async def remove_alerts_from_group(
    id: str,
    request: RemoveAlertsFromGroupRequest,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> RemoveAlertsFromGroupResponse:
    """
    Remove alerts from an existing alert group.

    This endpoint allows users to remove alerts from a group, making them ungrouped.

    Args:
        id: Alert group ID
        request: List of alert IDs to remove
        current_user: Authenticated user
        session: AsyncSession Database session

    Returns:
        Updated group information

    Raises:
        HTTPException: 404 if group not found, 400 if alerts don't exist or aren't in the group
    """
    try:
        logger.info(
            f"Removing {len(request.alert_ids)} alerts from group {id}, user: {current_user}"
        )

        # Get the group
        group = await session.scalar(
            select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group {id} not found"
            )

        # Check if group is being triaged
        if group.triage_status == "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify group while triage is in progress"
            )

        # Get current alert count in the group
        current_count_result = await session.execute(
            select(func.count(AlertDBModel.id)).where(AlertDBModel.group_id == group.id)
        )
        current_alert_count = current_count_result.scalar() or 0

        # Check if removing alerts would leave less than 2 alerts in the group
        remaining_count = current_alert_count - len(request.alert_ids)
        if remaining_count < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot remove alerts. A group must have at least 2 alerts. "
                       f"Current: {current_alert_count}, Trying to remove: {len(request.alert_ids)}, "
                       f"Would remain: {remaining_count}. Consider deleting the group instead."
            )

        # Validate all alerts exist
        alert_int_ids = [int(aid) for aid in request.alert_ids]

        alerts_query = select(AlertDBModel).where(
            AlertDBModel.id.in_(alert_int_ids)
        )
        result = await session.execute(alerts_query)
        alerts = result.scalars().all()

        if len(alerts) != len(alert_int_ids):
            found_ids = {a.id for a in alerts}
            missing_ids = set(alert_int_ids) - found_ids
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Alerts not found: {missing_ids}"
            )

        # Check if alerts are in this group
        not_in_group = [str(a.id) for a in alerts if a.group_id != group.id]
        if not_in_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Some alerts are not in this group: {not_in_group}"
            )

        # Remove alerts from the group (set group_id to NULL)
        for alert in alerts:
            alert.group_id = None

        await session.commit()

        # Get remaining alert count
        remaining_alerts_result = await session.execute(
            select(func.count(AlertDBModel.id)).where(AlertDBModel.group_id == group.id)
        )
        remaining_alerts = remaining_alerts_result.scalar() or 0

        logger.info(
            f"Removed {len(alerts)} alerts from group {id}. Remaining alerts: {remaining_alerts}"
        )

        return RemoveAlertsFromGroupResponse(
            group_id=group.id,
            group_name=group.group_name,
            alerts_removed=len(alerts),
            remaining_alerts=remaining_alerts,
            message=f"Successfully removed {len(alerts)} alerts from group '{group.group_name}'"
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to remove alerts from group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove alerts from group"
        )


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_alert_group(
    id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    Delete an alert group and ungroup all its alerts.

    This endpoint deletes the alert group and sets all its alerts' group_id to NULL,
    making them individual ungrouped alerts again.

    Args:
        id: Alert group ID
        current_user: Authenticated user
        session: Database session

    Returns:
        Success message with count of ungrouped alerts

    Raises:
        HTTPException: 404 if group not found, 400 if group is being triaged
    """
    try:
        logger.info(f"Deleting alert group {id}, user: {current_user}")

        # Get the group
        group = await session.scalar(
            select(AlertGroupDBModel).where(AlertGroupDBModel.id == int(id))
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert group {id} not found"
            )

        # Check if group is currently being triaged (processing state)
        if group.triage_status == "processing":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete group while triage is currently processing. Please wait for triage to complete."
            )

        # Get all alerts in the group
        alerts_query = select(AlertDBModel).where(AlertDBModel.group_id == group.id)
        result = await session.execute(alerts_query)
        alerts = result.scalars().all()

        alert_count = len(alerts)
        group_name = group.group_name

        # Ungroup all alerts (set group_id to NULL)
        for alert in alerts:
            alert.group_id = None

        # Delete the group
        await session.delete(group)
        await session.commit()

        logger.info(
            f"Deleted group {id} ('{group_name}'). Ungrouped {alert_count} alerts."
        )

        return {
            "message": f"Successfully deleted group '{group_name}'. {alert_count} alert(s) are now ungrouped.",
            "group_name": group_name,
            "alerts_ungrouped": alert_count
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to delete group {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete group"
        )

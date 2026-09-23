"""
Alert Manager Service API endpoints.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.server.apis_v1.dependencies import get_current_user, get_db_session
from src.server.apis_v1.helpers import (format_root_cause_analysis_content, format_group_root_cause_analysis_content,
                                        get_alert_by_id, get_formatted_triage_analysis_messages,
                                        get_latest_triage_record, get_eval_records_for_alert,
                                        get_latest_evaluation_record, get_latest_group_evaluation_record,
                                        generate_triage_thread_id)
from src.server.models.api.alert_details import AlertDetailResponse
from src.server.models.api.alert_list import AlertListItem, AlertListRequest, AlertListResponse, validate_custom_time_range
from src.server.models.api.alert_root_cause import TriageRCAResponse
from src.server.models.api.alert_traige import TriageJourneyResponse
from src.server.models.api.alert_triage_evaluation import TriageEvaluationResponse, ScoreCriteriaCard
from src.server.models.api.alert_create import ManualAlertCreateRequest, ManualAlertCreateResponse
from src.server.models.api.enums import Severity, Status, Timeline
from src.server.models.api.jobs import JobStatusResponse
from src.server.models.api.pagination_meta import PaginationMeta
from src.server.models.db import TriageDBModel, EvaluationDBModel, AlertDBModel, AlertGroupDBModel
from src.triage.triage_job import enqueue_triage_job
from src.triage_evaluation import enqueue_evaluation_job
from src.server.utilities.config import is_alert_grouping_enabled, is_automatic_triage_enabled
from pydantic import BaseModel, Field
from typing import List
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_manual_alert(
    request: ManualAlertCreateRequest,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> ManualAlertCreateResponse:
    """
    Create a manual alert.

    This endpoint allows users to manually create alerts from the UI.
    The alert will be created with a unique external_id and optionally
    enqueued for triage/grouping based on system configuration.

    Args:
        request: Manual alert creation request
        current_user: Authenticated user
        session: Database session

    Returns:
        ManualAlertCreateResponse with alert_id for navigation
    """
    try:
        logger.info(f"Creating manual alert: {request.alert_name}")

        # Step 1: Generate unique identifiers
        fingerprint = str(uuid.uuid4())
        timestamp = int(datetime.now(timezone.utc).timestamp())
        external_id = f"manual__{timestamp}__{fingerprint[:8]}"

        logger.info(f"Generated external_id: {external_id}")

        # Step 2: Build standard Grafana payload
        now_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "status": request.alert_status,
            "labels": {
                "alertname": request.alert_name,
                "severity": request.severity.value.lower(),




                **(request.labels or {})
            },
            "annotations": {
                "description": request.description,
                **(request.annotations or {})
            },
            "startsAt": now_iso,
            "endsAt": now_iso if request.alert_status == "resolved" else None,
            "fingerprint": fingerprint,
            "generatorURL": "manual"
        }

        # Step 3: Create alert record
        new_alert = AlertDBModel(
            external_id=external_id,
            payload=payload,
            alert_source="manual",
            alert_status=request.alert_status,
            severity=request.severity,
            alert_name=request.alert_name
        )

        session.add(new_alert)
        await session.flush()  # Get alert.id for triage enqueue

        logger.info(f"Created alert with ID: {new_alert.id}")

        # Step 4: Commit alert creation FIRST before triage logic
        # This prevents alert rollback if triage enqueueing fails
        try:
            await session.commit()
            logger.info(f"Alert {external_id} committed to database successfully")
        except Exception as e:
            await session.rollback()
            logger.exception(f"Database commit failed for alert {external_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save alert to database"
            )

        # Step 5: Handle triage (separate from alert creation transaction)
        triage_triggered = False

        # Only trigger triage for firing alerts (not resolved)
        if request.trigger_triage and request.alert_status == "firing":
            try:
                # Check if automatic triage is enabled (master switch)
                # Note: Config errors are logged but don't fail alert creation
                try:
                    automatic_triage = await is_automatic_triage_enabled()
                except Exception as config_error:
                    logger.error(f"Failed to load automatic_triage config: {config_error}", exc_info=True)
                    # Default to False on config errors - safer than enabling without verification
                    automatic_triage = False
                    logger.warning(f"Alert {external_id} created but triage disabled due to config error")

                if not automatic_triage:
                    logger.info(f"Alert {external_id} created but automatic triage is DISABLED - no triage job enqueued")
                    triage_triggered = False
                else:
                    # Check if alert grouping is enabled
                    try:
                        grouping_enabled = await is_alert_grouping_enabled()
                    except Exception as config_error:
                        logger.error(f"Failed to load alert_grouping config: {config_error}", exc_info=True)
                        # Default to True on config errors - allow grouping to proceed
                        grouping_enabled = True
                        logger.warning(f"Alert {external_id} defaulting to grouping mode due to config error")

                    if grouping_enabled:
                        # Alert will be processed by batch grouping worker
                        # Worker runs every 5 minutes and picks up all ungrouped alerts
                        logger.info(f"Alert {external_id} will be picked up by batch grouping worker")
                        triage_triggered = True
                    else:
                        # Alert grouping disabled - direct individual triage
                        # CRITICAL: Commit triage records BEFORE enqueueing job to prevent inconsistency
                        thread_id = generate_triage_thread_id(new_alert.id)

                        # Create Evaluation record BEFORE triage record (required by triage job)
                        new_evaluation = EvaluationDBModel()
                        new_evaluation.alert_id = new_alert.id  # type: ignore
                        new_evaluation.job_id = ""  # type: ignore
                        new_evaluation.status = Status.PENDING  # type: ignore
                        session.add(new_evaluation)

                        # Create Triage record before enqueueing job
                        new_triage = TriageDBModel()
                        new_triage.alert_id = new_alert.id  # type: ignore
                        new_triage.thread_id = thread_id  # type: ignore
                        new_triage.job_id = ""  # type: ignore
                        new_triage.status = Status.QUEUED  # type: ignore
                        session.add(new_triage)

                        # Flush to get IDs
                        await session.flush()

                        # Commit triage records to database BEFORE enqueueing job
                        # This ensures job will find the records when it runs
                        try:
                            await session.commit()
                            logger.info(f"Triage records committed for alert {external_id}")
                        except Exception as commit_error:
                            await session.rollback()
                            logger.error(f"Failed to commit triage records for alert {external_id}: {commit_error}", exc_info=True)
                            raise  # Will be caught by outer exception handler

                        # NOW enqueue the job - records are guaranteed to exist in DB
                        job_id = enqueue_triage_job(new_alert.id, thread_id, "high_priority_triages")

                        # Validate that job was actually enqueued
                        if not job_id:
                            logger.error(f"enqueue_triage_job returned empty job_id for alert {external_id}")
                            raise ValueError("enqueue_triage_job returned empty job_id")

                        # Update triage record with job_id (need new transaction)
                        new_triage.job_id = job_id  # type: ignore
                        try:
                            await session.commit()
                            logger.info(f"Enqueued individual triage job for alert {external_id}: job_id={job_id}, thread_id={thread_id}")
                            triage_triggered = True
                        except Exception as update_error:
                            # Job is already queued, just log the failure to update job_id
                            logger.warning(f"Triage job {job_id} enqueued but failed to update job_id in DB: {update_error}")
                            triage_triggered = True  # Job is running, so consider it triggered

            except Exception as e:
                # Log triage failure but don't fail the alert creation
                # The alert is already committed and exists in the database
                logger.error(f"Failed to enqueue triage for alert {external_id}: {e}", exc_info=True)
                triage_triggered = False

        logger.info(f"Successfully created manual alert: {external_id}, triage_triggered={triage_triggered}")

        # Step 6: Return response
        return ManualAlertCreateResponse(
            success=True,
            message="Alert created successfully",
            alert_id=external_id,
            triage_triggered=triage_triggered
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to create manual alert")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create alert"
        )


class CreateManualGroupRequest(BaseModel):
    """Request model for creating a manual group from selected alerts"""
    alert_ids: List[str] = Field(description="List of alert IDs to group together", min_length=1)
    group_name: str = Field(description="Name for the new group", min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, description="Optional description for the group")


class CreateManualGroupResponse(BaseModel):
    """Response model for manual group creation"""
    group_id: int = Field(description="ID of the created group")
    group_name: str = Field(description="Name of the created group")
    alert_count: int = Field(description="Number of alerts in the group")
    message: str = Field(description="Success message")


@router.get("/all")
async def list_all_alerts(
        request: AlertListRequest = Depends(),
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> AlertListResponse:
    """
    List ALL alerts (both grouped and ungrouped) with filtering and pagination.
    """
    return await _list_alerts_internal(request, current_user, session, include_grouped=True)


@router.get("")
async def list_alerts(
        request: AlertListRequest = Depends(),
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> AlertListResponse:
    """
    List ungrouped alerts only with filtering and pagination.
    """
    return await _list_alerts_internal(request, current_user, session, include_grouped=False)


async def _list_alerts_internal(
        request: AlertListRequest,
        current_user: str,
        session: AsyncSession,
        include_grouped: bool = False
) -> AlertListResponse:
    """
    Internal function to list alerts with filtering and pagination.

    Args:
        request: Alert list request parameters
        current_user: Current authenticated user
        session: Database session
        include_grouped: If True, include grouped alerts; if False, only ungrouped
    """
    # Validate custom time range parameters
    is_valid, error_msg = validate_custom_time_range(request.time_range, request.start_time, request.end_time)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    try:
        logger.info(f"Fetching alerts for user: {current_user}")

        # Build base query

        query = select(AlertDBModel).options(
            joinedload(AlertDBModel.triage_sessions),
            joinedload(AlertDBModel.evaluations),
            joinedload(AlertDBModel.group).joinedload(AlertGroupDBModel.evaluations)  # Load group and its evaluations
        )

        logger.info(f"SQL Query: {query.compile(compile_kwargs={'literal_binds': True})}")
        count_query = select(func.count(AlertDBModel.id))

        # filters
        filters = []

        # Filter by grouped status based on parameter
        if not include_grouped:
            # Only show ungrouped alerts (default behavior)
            filters.append(AlertDBModel.group_id.is_(None))
        # If include_grouped is True, we show all alerts (no group_id filter)

        # Timeline filter
        if request.time_range:
            cutoff_time = _get_timeline_cutoff(request.time_range, request.start_time)
            logger.info(f"Timeline filter: cutoff_time={cutoff_time}")
            filters.append(AlertDBModel.created_at >= cutoff_time)

            # For custom range, also apply end_time filter (exclusive, consistent with stats.py)
            if request.time_range == Timeline.CUSTOM and request.end_time:
                logger.info(f"Custom timeline filter: start={request.start_time}, end={request.end_time}")
                filters.append(AlertDBModel.created_at < request.end_time)

        if request.severity:
            # Filter by severity column directly (P1, P2, P3)
            filters.append(AlertDBModel.severity == request.severity)
            logger.info(f"Added severity filter for: {request.severity}")

        # Name contains filter (search in alert name from payload)
        if request.name_contains:
            # Search in commonLabels.alertname or alert_name column
            filters.append(
                or_(
                    AlertDBModel.payload["commonLabels"]["alertname"].astext.ilike(f"%{request.name_contains}%"),
                    AlertDBModel.alert_name.ilike(f"%{request.name_contains}%")
                )
            )

        if request.triage_status:
            # Map API triage status to group triage status
            # API uses: success, pending, processing, error, queued
            # Group uses: completed, pending, in_progress, failed
            status_to_group_status = {
                Status.SUCCESS: "completed",
                Status.PENDING: "pending",
                Status.PROCESSING: "in_progress",
                Status.ERROR: "failed",
                Status.QUEUED: "queued"
            }

            group_triage_status = status_to_group_status.get(request.triage_status)

            # Create a subquery to get the latest triage record per alert
            latest_triage_subquery = (
                select(
                    TriageDBModel.alert_id,
                    TriageDBModel.status,
                    func.row_number().over(
                        partition_by=TriageDBModel.alert_id,
                        order_by=TriageDBModel.created_at.desc()
                    ).label('rn')
                )
                .select_from(TriageDBModel)
            ).subquery()

            # Filter alerts where the latest triage (rn=1) has the requested status
            latest_triage_filter = (
                select(latest_triage_subquery.c.alert_id)
                .where(
                    and_(
                        latest_triage_subquery.c.rn == 1,
                        latest_triage_subquery.c.status == request.triage_status
                    )
                )
            )

            # Also include alerts that are in groups with matching triage status
            # This matches the display logic in _convert_db_alert_to_api_model
            triage_conditions = [
                AlertDBModel.id.in_(latest_triage_filter)  # Individual alert triage
            ]

            if group_triage_status:
                # Also include alerts whose group has the matching triage status
                triage_conditions.append(
                    and_(
                        AlertDBModel.group_id.is_not(None),
                        AlertDBModel.group.has(
                            AlertGroupDBModel.triage_status == group_triage_status
                        )
                    )
                )

            # Combine conditions with OR (alert has triage OR is in group with triage)
            filters.append(or_(*triage_conditions))

        if (request.evaluation_score_operator is None) != (request.evaluation_score_value is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation error: {Status.ERROR.value} - Both evaluation_score_operator and evaluation_score_value must be provided together"
            )

        # Handle evaluation filtering - consolidate status and score filtering
        evaluation_conditions = []

        # If evaluation_status is specified, add status condition
        if request.evaluation_status:
            evaluation_conditions.append(EvaluationDBModel.status == request.evaluation_status)

        # Only apply score filtering if evaluation_status is not specified or is "success"
        # Score filtering doesn't make sense for other statuses like pending, error, etc.
        should_apply_score_filter = (
                request.evaluation_score_operator is not None and
                request.evaluation_score_value is not None and
                (not request.evaluation_status or request.evaluation_status == Status.SUCCESS)
        )

        if should_apply_score_filter:
            # Use SQLAlchemy case() function for score filtering
            # For score filtering, we need success status
            if not request.evaluation_status:
                evaluation_conditions.append(EvaluationDBModel.status == Status.SUCCESS)

            # Build the score filter condition using SQLAlchemy case() function
            operator_map = {
                ">": lambda avg_score, value: avg_score > value,
                "<": lambda avg_score, value: avg_score < value,
                ">=": lambda avg_score, value: avg_score >= value,
                "<=": lambda avg_score, value: avg_score <= value
            }

            operator_func = operator_map.get(request.evaluation_score_operator)
            if not operator_func:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid evaluation_score_operator: {request.evaluation_score_operator}"
                )

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

            # Sum non-null score fields (using COALESCE to treat NULL as 0)
            score_sum = (
                    func.coalesce(EvaluationDBModel.root_cause_similarity_percent, 0) +
                    func.coalesce(EvaluationDBModel.orch_agent_util_score_percent, 0) +
                    func.coalesce(EvaluationDBModel.orch_task_completion_score_percent, 0) +
                    func.coalesce(EvaluationDBModel.sub_agent_tool_util_score_percent, 0) +
                    func.coalesce(EvaluationDBModel.sub_agent_task_completion_score, 0)
            )

            # Calculate average score, avoiding division by zero
            avg_score = case(
                (non_null_count > 0, score_sum / func.nullif(non_null_count, 0)),
                else_=None
            )

            # Apply the score filter condition
            score_condition = case(
                (avg_score.is_not(None), operator_func(avg_score, score_value)),
                else_=False
            )

            evaluation_conditions.append(score_condition)

        # Add consolidated evaluation filter if any conditions exist
        if evaluation_conditions:
            # For score filtering, we need to handle grouped and ungrouped alerts separately
            # because the score calculation is complex and doesn't work well through relationships

            if should_apply_score_filter:
                # Get alert IDs that match score filter (standalone alerts)
                standalone_alerts_query = (
                    select(AlertDBModel.id)
                    .where(AlertDBModel.group_id.is_(None))
                    .where(AlertDBModel.evaluations.any(and_(*evaluation_conditions)))
                )

                # Get alert IDs from groups that match score filter
                grouped_alerts_query = (
                    select(AlertDBModel.id)
                    .join(AlertGroupDBModel, AlertDBModel.group_id == AlertGroupDBModel.id)
                    .where(AlertGroupDBModel.evaluations.any(and_(*evaluation_conditions)))
                )

                # Combine: alerts with matching evaluations OR alerts in groups with matching evaluations
                filters.append(
                    or_(
                        AlertDBModel.id.in_(standalone_alerts_query),
                        AlertDBModel.id.in_(grouped_alerts_query)
                    )
                )
            else:
                # For non-score evaluation filters (just status), use the simpler approach
                eval_filter_conditions = [
                    AlertDBModel.evaluations.any(and_(*evaluation_conditions))
                ]

                eval_filter_conditions.append(
                    and_(
                        AlertDBModel.group_id.is_not(None),
                        AlertDBModel.group.has(
                            AlertGroupDBModel.evaluations.any(and_(*evaluation_conditions))
                        )
                    )
                )

                filters.append(or_(*eval_filter_conditions))

        # Note: ungrouped_only filter is now redundant as we always filter ungrouped alerts (line 87)

        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Get total count
        logger.info(f"Executing count query with {len(filters)} filters")
        total_result = await session.execute(count_query)
        total_items = total_result.scalar()
        logger.info(f"Total items found: {total_items}")

        # Debug: Test query without filters
        if total_items == 0:
            logger.info(
                "No items found with filters, testing without filters...")
            no_filter_query = select(func.count(AlertDBModel.id))
            no_filter_result = await session.execute(no_filter_query)
            no_filter_count = no_filter_result.scalar()
            logger.info(f"Total items without filters: {no_filter_count}")

        # Apply pagination
        offset = (request.page - 1) * request.page_size
        query = query.offset(offset).limit(
            request.page_size).order_by(AlertDBModel.created_at.desc())

        # Execute query
        result = await session.execute(query)
        db_alerts = result.unique().scalars().all()

        # Convert to API models
        alert_items = []
        for db_alert in db_alerts:
            try:
                alert_item = await _convert_db_alert_to_api_model(db_alert)
                alert_items.append(alert_item)
            except Exception as e:
                logger.warning(f"Failed to convert alert {db_alert.id}: {e}")
                continue

        # Build response
        pagination = PaginationMeta(
            current_page=request.page,
            page_size=request.page_size,
            total_items=total_items
        )

        response = AlertListResponse(
            alerts=alert_items,
            pagination=pagination
        )

        logger.info(
            f"Returning {len(alert_items)} alerts, total: {total_items}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch alerts from database")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch alerts: {str(e)}"
        )


@router.get("/{id}")
async def get_alert(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> AlertDetailResponse:
    """
    Get single alert details by ID or external_id.

    Args:
        id: Alert database ID or external_id
        current_user: Authenticated user
        session: Database session

    Returns:
        Detailed alert information

    Raises:
        HTTPException: 404 if alert not found, 500 for server errors
    """
    try:
        logger.info(f"Fetching alert details for ID: {id}, user: {current_user}")

        # Try to parse as integer ID first, otherwise use as external_id
        try:
            numeric_id = int(id)
            query = select(AlertDBModel).options(
                joinedload(AlertDBModel.triage_sessions),
                joinedload(AlertDBModel.evaluations),
                joinedload(AlertDBModel.group).joinedload(AlertGroupDBModel.evaluations)
            ).where(AlertDBModel.id == numeric_id)
        except ValueError:
            # Not a number, treat as external_id
            query = select(AlertDBModel).options(
                joinedload(AlertDBModel.triage_sessions),
                joinedload(AlertDBModel.evaluations),
                joinedload(AlertDBModel.group).joinedload(AlertGroupDBModel.evaluations)
            ).where(AlertDBModel.external_id == id)

        result = await session.execute(query)
        alert = result.unique().scalar_one_or_none()

        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert with ID '{id}' not found"
            )

        # Convert to API model
        alert_detail = await _convert_db_alert_to_detail_model(alert)

        logger.info(f"Successfully retrieved alert details for ID: {id}")
        return alert_detail

    except HTTPException:

        # Re-raise HTTP exceptions
        raise

    except Exception:

        logger.exception(f"Failed to fetch alert details for ID {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch alert details"
        )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
):
    """
    Delete alert by ID or external_id.

    Args:
        id: Alert ID or external_id to delete
        current_user: Authenticated user
        session: Database session

    Returns:
        Success message with deletion details

    Raises:
        HTTPException: If alert not found
    """
    try:

        # Try to parse as integer ID first, otherwise use as external_id
        try:
            numeric_id = int(id)
            query = select(AlertDBModel).where(AlertDBModel.id == numeric_id)
        except ValueError:
            # Not a number, treat as external_id
            query = select(AlertDBModel).where(AlertDBModel.external_id == id)

        result = await session.execute(query)
        alert = result.scalar_one_or_none()

        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert with id '{id}' not found"
            )

        # Delete the alert
        await session.delete(alert)
        await session.commit()

        logger.info(f"Alert {id} deleted by user {current_user}")

        return

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except Exception:
        logger.exception(f"Failed to delete alert {id}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete alert"
        )


@router.get("/{id}/root-cause")
async def get_alert_root_cause(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> TriageRCAResponse:
    """
    Get root cause analysis for an alert.

    If the alert belongs to a group, returns the group's RCA instead.

    Args:
        id: Alert identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Root cause analysis information in markdown format

    Raises:
        HTTPException: 404 if alert not found, 500 for server errors
    """
    try:
        logger.info(
            f"Getting root cause analysis for alert {id}, user: {current_user}")

        # Get alert from database
        alert = await get_alert_by_id(id, session)

        # Check if alert belongs to a group
        if alert.group_id:
            # Fetch the group
            from src.server.models.db import AlertGroupDBModel
            group = await session.scalar(
                select(AlertGroupDBModel).where(AlertGroupDBModel.id == alert.group_id)
            )

            if group:
                # Return group's RCA
                content = format_group_root_cause_analysis_content(group)
                return TriageRCAResponse(content=content)

        # Get the latest triage record for this alert (individual triage)
        latest_triage = await session.scalar(
            select(TriageDBModel)
            .where(TriageDBModel.alert_id == alert.id)
            .order_by(TriageDBModel.created_at.desc())
        )

        # Generate markdown content based on triage status
        content = format_root_cause_analysis_content(latest_triage)

        return TriageRCAResponse(content=content)

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to get root cause for alert {id}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve root cause analysis"
        )


@router.get("/{id}/triage")
async def get_alert_triage(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> TriageJourneyResponse:
    """
    Get triage journey for a specific alert.

    If the alert belongs to a group, returns the group's triage journey instead.

    Args:
        id: Alert identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Triage journey information

    Raises:
        HTTPException: 404 if alert not found, 500 for server errors
    """
    try:
        logger.info(f"Getting triage journey for alert {id}, user: {current_user}")

        # Get alert from database
        alert = await get_alert_by_id(id, session)

        # Check if alert belongs to a group
        if alert.group_id:
            # Fetch the group
            from src.server.models.db import AlertGroupDBModel
            group = await session.scalar(
                select(AlertGroupDBModel).where(AlertGroupDBModel.id == alert.group_id)
            )

            if group and group.thread_id:
                # Return group's triage journey
                messages = await get_formatted_triage_analysis_messages(group.thread_id)
                return TriageJourneyResponse(
                    alert_id=id,
                    messages=messages
                )

        # Get the latest triage record for this alert (individual triage)
        triage_record = await session.scalar(
            select(TriageDBModel)
            .where(TriageDBModel.alert_id == alert.id)
            .order_by(TriageDBModel.created_at.desc())
        )

        messages = []

        # Get triage analysis data if we have a thread_id
        if triage_record and triage_record.thread_id:
            thread_id_str = str(triage_record.thread_id)
            messages = await get_formatted_triage_analysis_messages(thread_id_str)

        return TriageJourneyResponse(
            alert_id=id,
            messages=messages
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to get triage journey for alert {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve triage journey"
        )


@router.get("/{id}/evaluation")
async def get_alert_evaluation(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> TriageEvaluationResponse:
    """
    Get evaluation details for an alert.

    If the alert belongs to a group, returns the group's evaluation instead.

    Args:
        id: Alert identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Evaluation details with score cards for non-null scores only

    Raises:
        HTTPException: 404 if alert not found, 500 for server errors
    """
    try:
        logger.info(f"Getting evaluation details for alert {id}, user: {current_user}")

        # Get alert from database
        alert = await get_alert_by_id(id, session)

        # Check if alert belongs to a group
        if alert.group_id:
            # Alert is part of a group - return the group's evaluation
            logger.info(f"Alert {id} belongs to group {alert.group_id}, fetching group evaluation")

            # Get the group with evaluations eagerly loaded
            group = await session.scalar(
                select(AlertGroupDBModel)
                .options(joinedload(AlertGroupDBModel.evaluations))
                .where(AlertGroupDBModel.id == alert.group_id)
            )

            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Alert group {alert.group_id} not found"
                )

            # Get the latest evaluation record for the group
            latest_evaluation = await get_latest_group_evaluation_record(group.id, session)  # type: ignore
        else:
            # Get the latest evaluation record for this alert
            latest_evaluation = await get_latest_evaluation_record(alert.id, session)  # type: ignore

        if latest_evaluation is None:
            # No evaluation exists yet
            if alert.group_id:
                reason = f"No evaluation has been performed for this alert's group (Group ID: {alert.group_id}) yet."
            else:
                reason = "No evaluation has been performed for this alert yet."

            return TriageEvaluationResponse(
                average_score_percent=0.0,
                reason=reason,
                score_criteria_cards=[]
            )

        if latest_evaluation.status != Status.SUCCESS:
            # Evaluation exists but not successful
            status_messages = {
                Status.PENDING: "Evaluation is currently pending.",
                Status.QUEUED: "Evaluation has been queued and will start processing soon.",
                Status.PROCESSING: "Evaluation is currently in progress.",
                Status.ERROR: "Evaluation failed with an error."
            }
            return TriageEvaluationResponse(
                average_score_percent=0.0,
                reason=status_messages.get(latest_evaluation.status, "Evaluation is not yet complete."),
                score_criteria_cards=[]
            )

        # Build score criteria cards for non-null scores only
        score_criteria_cards = []

        # Define score mappings with titles and descriptions
        score_mappings = [
            {
                "value": latest_evaluation.root_cause_similarity_percent,
                "title": "Root Cause Similarity",
                "description": "Measures the accuracy of AI-generated root cause analysis against expected outcomes."
            },
            {
                "value": latest_evaluation.orch_agent_util_score_percent,
                "title": "Orchestrator Agent Utilization",
                "description": "Evaluates the orchestrator's effectiveness in coordinating specialized agents and "
                               "leveraging knowledge base resources."
            },
            {
                "value": latest_evaluation.orch_task_completion_score_percent,
                "title": "Orchestrator Task Completion",
                "description": "Assesses the orchestrator's performance in completing the comprehensive "
                               "alert triage workflow."
            },
            {
                "value": latest_evaluation.sub_agent_tool_util_score_percent,
                "title": "Sub-Agent Tool Utilization",
                "description": "Evaluates specialized agents' proficiency in utilizing assigned tools and "
                               "resources for their specific tasks."
            },
            {
                "value": latest_evaluation.sub_agent_task_completion_score,
                "title": "Sub-Agent Task Completion",
                "description": "Measures the effectiveness of specialized agents in executing their designated "
                               "responsibilities within the triage process."
            }
        ]

        # Create cards only for non-null scores
        valid_scores = []
        for score_info in score_mappings:
            if score_info["value"] is not None:
                score_criteria_cards.append(ScoreCriteriaCard(
                    title=score_info["title"],
                    score_percent=score_info["value"],
                    description=score_info["description"]
                ))
                valid_scores.append(score_info["value"])

        # Calculate average score from non-null scores
        if valid_scores:
            average_score = round(sum(valid_scores) / len(valid_scores), 0)
            base_reason = latest_evaluation.reason or "Evaluation completed successfully."

            # Add note if showing group evaluation for an alert
            if alert.group_id:
                reason = f"Showing group-level evaluation (Group ID: {alert.group_id}). {base_reason}"
            else:
                reason = base_reason
        else:
            average_score = 0
            if alert.group_id:
                reason = f"No valid evaluation scores available for group {alert.group_id}."
            else:
                reason = "No valid evaluation scores available."

        return TriageEvaluationResponse(
            average_score_percent=average_score,
            reason=reason,
            score_criteria_cards=score_criteria_cards
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to get evaluation details for alert {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve evaluation details"
        )


@router.post("/{id}/triage", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_triage(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> JobStatusResponse:
    """
    Trigger manual triage analysis for a specific alert.

    Args:
        id: Alert identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Triage job information

    Raises:
        HTTPException: 404 if alert not found, 409 if triage already in progress, 500 for server errors
    """
    try:
        logger.info(f"Triggering manual triage for alert {id}, user: {current_user}")

        # Get alert from database
        alert = await get_alert_by_id(id, session)

        # Check if alert is part of a group
        if alert.group_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot triage alert '{id}' individually because it is part of alert group '{alert.group_id}'. "
                       f"Please triage the entire group instead by clicking 'Retriage' on the group page."
            )

        # Check if the latest triage is actively in progress (QUEUED or PROCESSING)
        # PENDING status means job was never enqueued, so we allow re-trigger
        latest_triage = await session.scalar(
            select(TriageDBModel)
            .where(TriageDBModel.alert_id == alert.id)
            .order_by(TriageDBModel.created_at.desc())
        )

        if latest_triage and latest_triage.status in [Status.QUEUED, Status.PROCESSING]:
            # Triage is already in progress (actively queued or processing)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Triage analysis {latest_triage.status.value} for alert '{id}'"
            )

        # Get old triage IDs for this alert (to delete them and their checkpoints)
        # This is done after the conflict check to avoid unnecessary DB queries
        old_triage_ids_result = await session.scalars(
            select(TriageDBModel.id)
            .where(TriageDBModel.alert_id == alert.id)
        )
        old_triage_ids = list(old_triage_ids_result.all())

        # Generate thread ID for this analysis session
        thread_id = generate_triage_thread_id(alert.id)

        # Create a new Triage record in the database BEFORE enqueuing the job
        # This ensures the triage entry exists and is populated before the job starts
        # Status is QUEUED (not PENDING) because we're about to enqueue the job
        # Worker will update to PROCESSING when it picks up the job
        new_triage = TriageDBModel()
        new_triage.thread_id = thread_id  # type: ignore
        new_triage.alert_id = alert.id  # type: ignore
        new_triage.job_id = ""  # type: ignore
        new_triage.status = Status.QUEUED  # type: ignore (job is queued, not pending)
        session.add(new_triage)

        # Create a new Evaluation record in the database so that triage job can find it
        # Check if evaluation already exists for this alert
        existing_evaluation = await session.scalar(
            select(EvaluationDBModel)
            .where(EvaluationDBModel.alert_id == alert.id)
        )

        if not existing_evaluation:
            new_evaluation = EvaluationDBModel()
            new_evaluation.alert_id = alert.id  # type: ignore
            new_evaluation.job_id = ""  # type: ignore
            new_evaluation.status = Status.PENDING  # type: ignore
            session.add(new_evaluation)

        await session.commit()

        # Now enqueue the triage analysis job
        job_id = enqueue_triage_job(
            alert_id=alert.id,  # type: ignore
            triage_id=thread_id,
            queue_name="high_priority_triages"  # High priority for manual triage
        )

        # Update the triage record with the job_id and status to QUEUED
        new_triage.job_id = job_id  # type: ignore
        new_triage.status = Status.QUEUED  # type: ignore
        await session.commit()

        # Enqueue cleanup job AFTER triage job completes (using depends_on)
        # This ensures cleanup only runs after the new triage is finished
        cleanup_job_id = None
        if old_triage_ids:
            from src.server.async_workers.cleanup_job import enqueue_cleanup_job
            cleanup_job_id = enqueue_cleanup_job(old_triage_ids, depends_on_job_id=job_id)
            logger.info(
                f"Manual triage job enqueued: job_id={job_id}, thread_id={new_triage.thread_id}, alert_id={id}, "
                f"cleanup_job_id={cleanup_job_id} (will run after triage completes)")
        else:
            logger.info(f"Manual triage job enqueued: job_id={job_id}, thread_id={new_triage.thread_id}, alert_id={id}")

        return JobStatusResponse(
            job_id=job_id,
            status="queued"
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to trigger triage for alert {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger triage analysis"
        )


@router.post("/{id}/evaluation", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_evaluation(
        id: str,
        current_user: str = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)
) -> JobStatusResponse:
    """
    Trigger manual triage analysis for a specific alert.

    Args:
        id: Alert identifier
        current_user: Authenticated user
        session: Database session

    Returns:
        Triage job information

    Raises:
        HTTPException: 404 if alert not found, 409 if triage already in progress, 500 for server errors
    """
    try:
        logger.info(f"Triggering manual evaluation for alert {id}, user: {current_user}")

        # Get alert from database
        alert = await get_alert_by_id(id, session)

        latest_triage_record = await get_latest_triage_record(alert.id, session)

        if latest_triage_record and latest_triage_record.status != Status.SUCCESS:  # type: ignore
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Triage not completed for alert '{id}'"
            )

        # Check if evaluation is already in progress
        # type: ignore
        eval_records = await get_eval_records_for_alert(alert.id, session)

        # Check if the latest evaluation is already active (pending/processing)
        # Only check the most recent evaluation record to allow re-evaluation of failed attempts
        if eval_records:
            latest_evaluation = eval_records[0]  # Already ordered by created_at desc
            if latest_evaluation.status in [Status.QUEUED, Status.PROCESSING]:  # type: ignore
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Evaluation {latest_evaluation.status} for alert '{id}'"
                )

        # Create a new Evaluation record in the database BEFORE enqueuing the job
        # This ensures the evaluation entry exists and is populated before the job starts
        new_eval = EvaluationDBModel()
        new_eval.alert_id = alert.id  # type: ignore
        new_eval.job_id = ""  # type: ignore
        new_eval.status = Status.PENDING  # type: ignore

        session.add(new_eval)

        await session.commit()

        # Now enqueue the evaluation job
        job_id = enqueue_evaluation_job(
            alert_id=alert.id  # type: ignore
        )

        # Update the evaluation record with the job_id and status to QUEUED
        new_eval.job_id = job_id  # type: ignore
        new_eval.status = Status.QUEUED  # type: ignore

        await session.commit()

        logger.info(f"Manual evaluation job enqueued: job_id={job_id}, alert_id={id}")

        return JobStatusResponse(
            job_id=job_id,
            status="queued"
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Failed to trigger evaluation for alert {id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger evaluation"
        )


def _get_timeline_cutoff(time_range: Timeline, start_time: Optional[datetime] = None) -> Optional[datetime]:
    """Convert timeline filter to datetime cutoff.

    Args:
        time_range: Timeline enum value
        start_time: Required when time_range is CUSTOM

    Returns:
        datetime cutoff for filtering, or start_time for CUSTOM range
    """
    if time_range == Timeline.CUSTOM:
        return start_time

    now = datetime.now(timezone.utc)
    timeline_map = {
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30)
    }

    delta = timeline_map.get(time_range, timedelta(hours=24))
    return now - delta


async def _convert_db_alert_to_api_model(db_alert: AlertDBModel) -> AlertListItem:
    """Convert database alert to API model."""
    payload = db_alert.payload
    labels = payload.get("labels", {})

    # ✅ FIX: Check for group evaluation if alert belongs to a group
    # This ensures the alert list shows the same evaluation score as the detail page
    latest_evaluation = None
    if db_alert.group_id and db_alert.group:
        # Alert is part of a group - use group's evaluation
        if db_alert.group.evaluations:
            latest_evaluation = max(db_alert.group.evaluations, key=lambda e: e.created_at)
    elif db_alert.evaluations:
        # Alert is standalone - use alert's own evaluation
        latest_evaluation = max(db_alert.evaluations, key=lambda e: e.created_at)

    if latest_evaluation is None:
        evaluation_status = Status.PENDING
        evaluation_score = None
    elif latest_evaluation.status == Status.ERROR:
        evaluation_status = Status.ERROR
        evaluation_score = None
    else:
        evaluation_status = latest_evaluation.status
        # Only calculate evaluation_score for successful evaluations
        if latest_evaluation.status == Status.SUCCESS:
            # Use the new score column names
            scores = [
                latest_evaluation.root_cause_similarity_percent,
                latest_evaluation.orch_agent_util_score_percent,
                latest_evaluation.orch_task_completion_score_percent,
                latest_evaluation.sub_agent_tool_util_score_percent,
                latest_evaluation.sub_agent_task_completion_score
            ]
            valid_scores = [s for s in scores if s is not None]
            if not valid_scores:
                evaluation_score = None
            else:
                # Return average score as percentage (0-100)
                evaluation_score = sum(valid_scores) / len(valid_scores)
        else:
            evaluation_score = None

    # Get triage status
    # ✅ FIX: Check if alert belongs to a group FIRST
    if db_alert.group_id and hasattr(db_alert, 'group') and db_alert.group:
        # Alert belongs to a group - use group's triage status
        if db_alert.group.triage_status == "completed":
            triage_status = Status.SUCCESS
        elif db_alert.group.triage_status == "in_progress":
            triage_status = Status.PROCESSING
        elif db_alert.group.triage_status == "failed":
            triage_status = Status.ERROR
        else:
            triage_status = Status.PENDING
    else:
        # Alert is standalone - check individual triage
        latest_triage = None
        if db_alert.triage_sessions:
            latest_triage = max(db_alert.triage_sessions, key=lambda t: t.created_at)

        if latest_triage is None:
            triage_status = Status.PENDING
        elif latest_triage.error_message:
            triage_status = Status.ERROR
        else:
            triage_status = latest_triage.status

    # Handle startsAt parsing more safely
    started_at = db_alert.created_at
    if "startsAt" in payload:
        try:
            started_at = datetime.fromisoformat(
                payload["startsAt"].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            started_at = db_alert.created_at

    # Use severity directly from database (already stored as P1/P2/P3)
    severity: Severity = db_alert.severity if db_alert.severity is not None else Severity.P3  # type: ignore

    return AlertListItem(
        id=str(db_alert.id),
        name=labels.get("alertname", db_alert.alert_name or "Unknown Alert"),
        severity=severity,
        triage_status=triage_status,
        evaluation_status=evaluation_status,
        evaluation_score=evaluation_score,
        started_at=started_at,  # type: ignore
        last_updated_at=db_alert.updated_at,  # type: ignore
        alert_source=str(db_alert.alert_source or "grafana")
    )


async def _convert_db_alert_to_detail_model(db_alert: AlertDBModel) -> AlertDetailResponse:
    """Convert database alert to detailed API model."""
    payload = db_alert.payload or {}
    labels = payload.get("labels", {})

    # Get evaluation status
    # ✅ FIX: Check if alert belongs to a group FIRST
    latest_evaluation = None

    if db_alert.group_id and hasattr(db_alert, 'group') and db_alert.group:
        # Alert belongs to a group - use group's evaluation
        if db_alert.group.evaluations:
            latest_evaluation = max(db_alert.group.evaluations, key=lambda e: e.created_at)
    elif db_alert.evaluations:
        # Alert is standalone - use alert's own evaluation
        latest_evaluation = max(db_alert.evaluations, key=lambda e: e.created_at)

    if latest_evaluation is None:
        evaluation_status = Status.PENDING
    elif latest_evaluation.status == Status.ERROR:
        evaluation_status = Status.ERROR
    else:
        evaluation_status = latest_evaluation.status

    # Get triage status
    # ✅ FIX: Check if alert belongs to a group FIRST
    if db_alert.group_id and hasattr(db_alert, 'group') and db_alert.group:
        # Alert belongs to a group - use group's triage status
        if db_alert.group.triage_status == "completed":
            triage_status = Status.SUCCESS
        elif db_alert.group.triage_status == "in_progress":
            triage_status = Status.PROCESSING
        elif db_alert.group.triage_status == "failed":
            triage_status = Status.ERROR
        else:
            triage_status = Status.PENDING
    else:
        # Alert is standalone - check individual triage
        latest_triage = None
        if db_alert.triage_sessions:
            latest_triage = max(db_alert.triage_sessions, key=lambda t: t.created_at)

        if latest_triage is None:
            triage_status = Status.PENDING
        elif latest_triage.error_message:
            triage_status = Status.ERROR
        else:
            triage_status = latest_triage.status

    # Handle startsAt parsing more safely
    started_at = db_alert.created_at
    if "startsAt" in payload:
        try:
            started_at = datetime.fromisoformat(
                payload["startsAt"].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            started_at = db_alert.created_at

    # Use severity directly from database (already stored as P1/P2/P3)
    severity: Severity = db_alert.severity if db_alert.severity is not None else Severity.P3  # type: ignore

    return AlertDetailResponse(
        id=str(db_alert.id),
        external_id=str(db_alert.external_id),
        name=labels.get("alertname", db_alert.alert_name or "Unknown Alert"),
        severity=severity,
        triage_status=triage_status,
        evaluation_status=evaluation_status,
        started_at=started_at,  # type: ignore
        created_at=db_alert.created_at,  # type: ignore
        last_updated_at=db_alert.updated_at,  # type: ignore
        alert_source=str(db_alert.alert_source or "grafana"),
        alert_status=str(db_alert.alert_status or "firing"),
        payload=payload  # type: ignore
    )


@router.post("/create-manual-group", status_code=status.HTTP_201_CREATED)
async def create_manual_group(
    request: CreateManualGroupRequest,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> CreateManualGroupResponse:
    """
    Create a manual alert group from selected alerts.

    This endpoint allows users to manually select multiple ungrouped alerts
    and create a new group for them. The alerts will be moved from ungrouped
    status to the new group.

    Args:
        request: List of alert IDs and group name
        current_user: Authenticated user
        session: Database session

    Returns:
        Created group information

    Raises:
        HTTPException: 400 if alerts don't exist or are already grouped,
                      500 for server errors
    """
    try:
        logger.info(
            f"Creating manual group '{request.group_name}' with {len(request.alert_ids)} alerts, user: {current_user}"
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
                detail=f"Cannot create group with alerts {already_triaged} because they have already been triaged. "
                       f"Grouping already-triaged alerts would lose their existing triage analysis."
            )

        # Determine group severity (highest severity among selected alerts)
        severities_order = {Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        group_severity = min(alerts, key=lambda a: severities_order.get(a.severity, 3)).severity

        # Create new alert group
        reasoning = request.description if request.description else f"Manually grouped by {current_user.username}"
        new_group = AlertGroupDBModel(
            group_name=request.group_name,
            severity=group_severity,
            status="active",
            triage_status="pending",
            grouping_confidence=1.0,  # Manual grouping has 100% confidence
            grouping_reasoning=reasoning
        )

        session.add(new_group)
        await session.flush()  # Get the group ID

        # Assign all alerts to the new group
        for alert in alerts:
            alert.group_id = new_group.id

        await session.commit()
        await session.refresh(new_group)

        logger.info(
            f"Manual group created successfully: group_id={new_group.id}, "
            f"name='{request.group_name}', alert_count={len(alerts)}"
        )

        return CreateManualGroupResponse(
            group_id=new_group.id,
            group_name=new_group.group_name,
            alert_count=len(alerts),
            message=f"Successfully created group '{request.group_name}' with {len(alerts)} alerts"
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to create manual group")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create manual group"
        )

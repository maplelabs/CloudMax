"""
Alert Grouping Service (Batch Queue-Based)

This service processes alerts from the Redis queue in BATCHES:
1. Dequeue ALL pending alert IDs from Redis queue
2. Fetch all alerts from database
3. Fetch active groups
4. Run LLM batch grouping analysis (one LLM call for all alerts)
5. Update database with group assignments for all alerts
6. Return results

CRITICAL CONSTRAINT: Groups must have ≥2 alerts (never create single-alert groups)

This is called by the grouping worker to process all queued alerts together.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.alert_grouping.models import (
    Alert as GroupingAlert,
    Severity as GroupingSeverity,
)
from src.alert_grouping.prompts import create_batch_grouping_prompt
from src.server.apis_v1.dependencies import async_db_session
from src.server.models.api import Severity
from src.server.models.db import AlertDBModel, AlertGroupDBModel
from src.server.utilities.llm_manager import get_primary_llm_async
from src.server.utilities.llm_response_parser import extract_json_from_markdown

logger = logging.getLogger(__name__)


def convert_db_alert_to_grouping_alert(db_alert: AlertDBModel) -> GroupingAlert:
    """Convert database alert model to grouping alert model."""
    severity_map = {
        Severity.P1: GroupingSeverity.P1,
        Severity.P2: GroupingSeverity.P2,
        Severity.P3: GroupingSeverity.P3,
    }

    payload = db_alert.payload or {}
    labels = payload.get("labels", {})
    annotations = payload.get("annotations", {})

    return GroupingAlert(
        id=f"alert-{db_alert.id}",
        alert_name=db_alert.alert_name or labels.get("alertname", "unknown"),
        severity=severity_map.get(db_alert.severity, GroupingSeverity.P3),
        alert_source=db_alert.alert_source or "unknown",
        status=db_alert.alert_status or "firing",
        labels=labels,
        annotations=annotations,
        starts_at=(
            db_alert.created_at if db_alert.created_at else datetime.now(timezone.utc)
        ),
        ends_at=None,
        fingerprint=payload.get("fingerprint", ""),
        group_id=None,
        raw_payload=payload,
    )


async def fetch_active_groups_with_alerts(
    session: AsyncSession, config=None
) -> List[Dict[str, Any]]:
    """
    Fetch active groups with sample alerts for LLM context.

    Only fetches groups that were CREATED within the lookback window (default: 30 minutes).
    This ensures we only consider recently created groups as candidates for adding new alerts,
    not old groups that just happened to be updated recently.

    IMPORTANT: Excludes groups with triage_status='in_progress' to prevent modifying
    groups that are currently being triaged.

    Uses eager loading (selectinload) to avoid N+1 query problem.
    """
    from sqlalchemy.orm import selectinload

    # Load config if not provided
    if config is None:
        from src.server.utilities.grouping_config import get_grouping_config_async

        config = await get_grouping_config_async()

    # Fetch groups created within the lookback window (from NOW - 30 min)
    # This ensures we only pass recently created groups to the LLM
    lookback_time = datetime.now(timezone.utc) - timedelta(
        minutes=config.active_groups_lookback_minutes
    )

    # OPTIMIZED: Use selectinload to avoid N+1 query problem
    stmt = (
        select(AlertGroupDBModel)
        .where(
            and_(
                AlertGroupDBModel.status.in_(["active", "resolved"]),
                AlertGroupDBModel.created_at
                >= lookback_time,  # Changed from updated_at to created_at
                AlertGroupDBModel.triage_status
                != "in_progress",  # Don't modify groups being triaged
            )
        )
        .options(selectinload(AlertGroupDBModel.alerts))  # Eager load all alerts
        .order_by(AlertGroupDBModel.created_at.desc())  # Order by creation time
        .limit(config.max_active_groups_context)
    )

    result = await session.execute(stmt)
    groups = result.scalars().all()

    groups_with_alerts = []
    for group in groups:
        # Alerts are already loaded - no additional query needed!
        # Sort alerts in Python (already in memory)
        # Limit to sample size for group summaries
        from src.alert_grouping.services.alert_grouping_constants import (
            MAX_ALERTS_PER_GROUP_SAMPLE,
        )

        alerts = sorted(
            group.alerts,
            key=lambda a: a.created_at if a.created_at else datetime.min,
            reverse=True,
        )[:MAX_ALERTS_PER_GROUP_SAMPLE]

        groups_with_alerts.append(
            {
                "group_id": group.id,
                "group_name": group.group_name,
                "status": group.status,
                "severity": group.severity.value if group.severity else "P3",
                "alert_count": len(
                    group.alerts
                ),  # Total count from loaded relationship
                "alerts": [
                    {
                        "id": f"alert-{alert.id}",
                        "alert_name": alert.alert_name,
                        "severity": alert.severity.value if alert.severity else "P3",
                        "timestamp": (
                            alert.created_at.isoformat() if alert.created_at else ""
                        ),
                        "labels": (
                            alert.payload.get("labels", {}) if alert.payload else {}
                        ),
                    }
                    for alert in alerts
                ],
                "created_at": group.created_at.isoformat() if group.created_at else "",
            }
        )

    logger.info(f"[Grouping] Found {len(groups_with_alerts)} active groups for context")
    return groups_with_alerts


async def process_batch_alerts_for_grouping_async(
    alert_ids: List[int],
) -> Dict[str, Any]:
    """
    Process multiple alerts for grouping in a single batch.

    Fetches the specified alerts and active groups (last 30 min), sends to LLM for
    grouping decisions, and applies the decisions to the database.

    Only recent groups are considered since older ungrouped alerts are handled
    by Job 2 (Ungrouped Retry).

    Args:
        alert_ids: List of alert IDs to process

    Returns:
        Dictionary with processing statistics
    """
    logger.info(
        f"[Batch Grouping] alert_ids={alert_ids} -> Processing {len(alert_ids)} alerts in batch"
    )

    stats = {
        "total_alerts": len(alert_ids),
        "new_groups_created": 0,
        "alerts_joined_existing": 0,
        "alerts_skipped": 0,
        "groups_needing_triage": set(),
        "skipped_alerts": [],
        "errors": [],
    }

    try:
        async with async_db_session() as session:
            # Fetch specified alerts
            stmt = select(AlertDBModel).where(AlertDBModel.id.in_(alert_ids))
            result = await session.execute(stmt)
            db_alerts = list(result.scalars().all())

            if not db_alerts:
                logger.warning(
                    f"[Batch Grouping] alert_ids={alert_ids} -> No alerts found in database"
                )
                return stats

            # Filter out already grouped alerts
            ungrouped_alerts = [a for a in db_alerts if a.group_id is None]

            if not ungrouped_alerts:
                logger.info(
                    f"[Batch Grouping] alert_ids={alert_ids} -> All {len(db_alerts)} alerts are already grouped"
                )
                return stats

            ungrouped_ids = [a.id for a in ungrouped_alerts]
            logger.info(
                f"[Batch Grouping] alert_ids={ungrouped_ids} -> Found {len(ungrouped_alerts)} ungrouped alerts to process"
            )

            # Fetch active groups from last 30 minutes
            existing_groups = await fetch_active_groups_with_alerts(session)
            logger.info(
                f"[Batch Grouping] alert_ids={ungrouped_ids} -> Found {len(existing_groups)} active groups for context"
            )

            # CRITICAL: Skip LLM call if there's nothing meaningful to group
            # Conditions where LLM call should be skipped:
            # 1. Less than 2 ungrouped alerts AND no existing groups to join
            #
            # Why: Groups must have ≥2 alerts, so we need either:
            # - 2+ ungrouped alerts to create a new group, OR
            # - 1+ ungrouped alert + existing groups to potentially join
            if len(ungrouped_alerts) < 2 and len(existing_groups) == 0:
                logger.info(
                    f"[Batch Grouping] alert_ids={ungrouped_ids} -> {len(ungrouped_alerts)} ungrouped alert(s) and no existing groups. "
                    "Skipping LLM call (cannot create single-alert group). Alert(s) will be retried later."
                )
                stats["alerts_skipped"] = len(ungrouped_alerts)
                for alert_id in ungrouped_ids:
                    stats["skipped_alerts"].append({
                        "alert_id": alert_id,
                        "reason": "insufficient_alerts_for_grouping",
                        "message": "Need at least 2 alerts to create a group, or existing groups to join",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                return stats

            # Step 3: Convert to grouping format
            grouping_alerts = [
                convert_db_alert_to_grouping_alert(a) for a in ungrouped_alerts
            ]

            # Create ID mapping (alert-123 -> 123)
            alert_id_map = {f"alert-{a.id}": a.id for a in ungrouped_alerts}

            # Step 4: Run batch grouping analysis
            logger.info(
                f"[Batch Grouping] alert_ids={ungrouped_ids} -> Calling LLM for batch grouping analysis..."
            )
            grouping_result = await run_batch_grouping_analysis(
                grouping_alerts, existing_groups
            )

            # Step 5: Apply decisions with constraint enforcement
            decisions = grouping_result.get("decisions", [])
            logger.info(
                f"[Batch Grouping] alert_ids={ungrouped_ids} -> LLM returned {len(decisions)} decisions"
            )

            # First pass: Collect all decisions to enforce ≥2 alerts per group
            temp_groups = {}  # temp_group_id -> list of alert_ids

            for decision in decisions:
                action = decision.get("action")
                alert_id = decision.get("alert_id")

                if action == "create_new_group":
                    temp_group_id = decision.get("temp_group_id")
                    if temp_group_id:
                        if temp_group_id not in temp_groups:
                            temp_groups[temp_group_id] = []
                        temp_groups[temp_group_id].append(alert_id)

                elif action == "join_group":
                    group_id = decision.get("group_id")
                    # If joining a temp group created in this batch
                    if isinstance(group_id, int) and group_id in temp_groups:
                        temp_groups[group_id].append(alert_id)

            # Check which temp groups have ≥2 alerts
            valid_temp_groups = {
                gid: alerts for gid, alerts in temp_groups.items() if len(alerts) >= 2
            }
            invalid_temp_groups = {
                gid: alerts for gid, alerts in temp_groups.items() if len(alerts) < 2
            }

            if invalid_temp_groups:
                logger.warning(
                    f"Skipping {len(invalid_temp_groups)} temp groups with <2 alerts: {invalid_temp_groups}"
                )

            # OPTIMIZATION: Create lookup dictionaries to avoid N+1 queries
            # Create alert lookup from already-fetched ungrouped_alerts
            alert_lookup = {a.id: a for a in ungrouped_alerts}

            # Pre-fetch all groups that will be needed (existing groups being joined)
            group_ids_to_fetch = set()
            for decision in decisions:
                if decision.get("action") == "join_group":
                    group_id = decision.get("group_id")
                    # Only fetch if it's not a temp group (temp groups will be created in this batch)
                    if group_id and not (
                        isinstance(group_id, int) and group_id in temp_groups
                    ):
                        group_ids_to_fetch.add(group_id)

            # Fetch all needed groups in ONE query
            group_lookup = {}
            if group_ids_to_fetch:
                stmt = select(AlertGroupDBModel).where(
                    AlertGroupDBModel.id.in_(group_ids_to_fetch)
                )
                result = await session.execute(stmt)
                group_lookup = {g.id: g for g in result.scalars().all()}
                logger.info(
                    f"[Batch Grouping] Pre-fetched {len(group_lookup)} existing groups in single query"
                )

            # Second pass: Apply decisions with validation
            temp_to_db_group_id = {}

            for decision in decisions:
                alert_id = decision.get("alert_id")
                action = decision.get("action")
                confidence = decision.get("confidence", 0.0)
                reasoning = decision.get("reasoning", "")

                # Get database alert ID
                db_alert_id = alert_id_map.get(alert_id)
                if not db_alert_id:
                    # HIGH PRIORITY: Track detailed skip reason
                    error_detail = {
                        "alert_id": alert_id,
                        "reason": "alert_id_mapping_failed",
                        "message": f"Alert {alert_id} not found in database",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    stats["skipped_alerts"].append(error_detail)
                    stats["alerts_skipped"] += 1
                    logger.warning(
                        f"Alert {alert_id} not found in alert_id_map, skipping"
                    )
                    continue

                # OPTIMIZED: Use lookup instead of SELECT query
                alert = alert_lookup.get(db_alert_id)
                if not alert:
                    # HIGH PRIORITY: Track detailed skip reason
                    error_detail = {
                        "alert_id": alert_id,
                        "db_alert_id": db_alert_id,
                        "reason": "alert_not_in_lookup",
                        "message": f"Alert {db_alert_id} not found in alert_lookup (possibly already grouped)",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    stats["skipped_alerts"].append(error_detail)
                    stats["alerts_skipped"] += 1
                    logger.warning(
                        f"Alert {db_alert_id} not found in alert_lookup, skipping"
                    )
                    continue

                if action == "create_new_group":
                    temp_group_id = decision.get("temp_group_id")

                    # CONSTRAINT CHECK: Only create if this temp group has ≥2 alerts
                    if temp_group_id not in valid_temp_groups:
                        # HIGH PRIORITY: Track detailed skip reason
                        error_detail = {
                            "alert_id": alert_id,
                            "db_alert_id": db_alert_id,
                            "reason": "temp_group_insufficient_alerts",
                            "message": f"Temp group {temp_group_id} has <2 alerts (constraint violation)",
                            "temp_group_id": temp_group_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        stats["skipped_alerts"].append(error_detail)
                        stats["alerts_skipped"] += 1
                        logger.info(
                            f"Skipping alert {alert_id}: temp_group {temp_group_id} has <2 alerts"
                        )
                        continue

                    # Check if we already created this temp group
                    if temp_group_id in temp_to_db_group_id:
                        # This alert should join the already-created group
                        actual_group_id = temp_to_db_group_id[temp_group_id]

                        # OPTIMIZED: Group was just created in this session, no need to query
                        # Just assign the alert to the group (group is already in session)
                        alert.group_id = actual_group_id
                        stats["alerts_joined_existing"] += 1
                        stats["groups_needing_triage"].add(actual_group_id)
                        logger.info(
                            f"Alert {alert_id} joined temp group {temp_group_id} (DB group {actual_group_id})"
                        )
                    else:
                        # Create new group
                        group_name = decision.get("group_name")
                        if not group_name:
                            # HIGH PRIORITY: Track detailed skip reason
                            error_detail = {
                                "alert_id": alert_id,
                                "db_alert_id": db_alert_id,
                                "reason": "missing_group_name",
                                "message": "LLM decision missing required 'group_name' field",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            stats["skipped_alerts"].append(error_detail)
                            stats["alerts_skipped"] += 1
                            logger.error(
                                f"create_new_group decision missing group_name for alert {alert_id}, skipping"
                            )
                            continue

                        new_group = AlertGroupDBModel(
                            group_name=group_name,
                            status="active",
                            severity=alert.severity,
                            triage_status="pending",
                            grouping_confidence=confidence,
                            grouping_reasoning=reasoning,
                        )
                        session.add(new_group)
                        await session.flush()  # Get the ID

                        # Assign alert to this group
                        alert.group_id = new_group.id
                        stats["new_groups_created"] += 1
                        stats["groups_needing_triage"].add(new_group.id)

                        # Map temporary ID to database ID
                        temp_to_db_group_id[temp_group_id] = new_group.id

                        logger.info(
                            f"Created new group {new_group.id}: '{group_name}' with alert {alert_id}"
                        )

                elif action == "join_group":
                    group_id = decision.get("group_id")
                    if group_id is None:
                        # HIGH PRIORITY: Track detailed skip reason
                        error_detail = {
                            "alert_id": alert_id,
                            "db_alert_id": db_alert_id,
                            "reason": "missing_group_id",
                            "message": "LLM decision missing required 'group_id' field",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        stats["skipped_alerts"].append(error_detail)
                        stats["alerts_skipped"] += 1
                        logger.error(
                            f"join_group decision missing group_id for alert {alert_id}, skipping"
                        )
                        continue

                    # Check if this is a temporary ID (from a group created in this batch)
                    if isinstance(group_id, int) and group_id in temp_to_db_group_id:
                        actual_group_id = temp_to_db_group_id[group_id]
                        # Group was just created in this batch - it's in the session, no query needed
                        group = None  # We'll just use the ID directly
                    elif isinstance(group_id, int) and group_id in valid_temp_groups:
                        # Temp group not yet created - skip this alert
                        # HIGH PRIORITY: Track detailed skip reason
                        error_detail = {
                            "alert_id": alert_id,
                            "db_alert_id": db_alert_id,
                            "reason": "temp_group_not_created",
                            "message": f"Temp group {group_id} hasn't been created yet",
                            "group_id": group_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        stats["skipped_alerts"].append(error_detail)
                        stats["alerts_skipped"] += 1
                        logger.warning(
                            f"Alert {alert_id} trying to join temp group {group_id} that hasn't been created yet, skipping"
                        )
                        continue
                    else:
                        actual_group_id = group_id
                        # OPTIMIZED: Use pre-fetched group lookup instead of SELECT query
                        group = group_lookup.get(actual_group_id)

                        if not group:
                            # HIGH PRIORITY: Track detailed skip reason
                            error_detail = {
                                "alert_id": alert_id,
                                "db_alert_id": db_alert_id,
                                "reason": "group_not_found",
                                "message": f"Group {actual_group_id} not found (possibly deleted or LLM hallucination)",
                                "group_id": actual_group_id,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            stats["skipped_alerts"].append(error_detail)
                            stats["alerts_skipped"] += 1
                            logger.error(
                                f"Group {actual_group_id} not found in group_lookup for alert {alert_id}, skipping"
                            )
                            continue

                    # Assign alert to group
                    alert.group_id = actual_group_id

                    # Update group metadata (only if we have the group object)
                    if group:
                        group.updated_at = datetime.now(timezone.utc)

                        # CRITICAL FIX: Escalate severity using priority-based comparison
                        # This now handles ALL severity levels (P1, P2, P3, P4)
                        severity_priority = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
                        current_priority = (
                            severity_priority.get(group.severity.value, 4)
                            if group.severity
                            else 4
                        )
                        new_priority = (
                            severity_priority.get(alert.severity.value, 4)
                            if alert.severity
                            else 4
                        )

                        # Escalate to higher priority (lower number = higher priority)
                        if new_priority < current_priority:
                            group.severity = alert.severity
                            logger.info(
                                f"Escalated group {actual_group_id} severity from {group.severity.value if group.severity else 'None'} to {alert.severity.value}"
                            )

                    stats["alerts_joined_existing"] += 1
                    stats["groups_needing_triage"].add(actual_group_id)

                    logger.info(f"Alert {alert_id} joined group {actual_group_id}")

                elif action == "skip":
                    # HIGH PRIORITY: Track detailed skip reason
                    error_detail = {
                        "alert_id": alert_id,
                        "db_alert_id": db_alert_id,
                        "reason": "llm_skip_decision",
                        "message": reasoning or "LLM decided to skip this alert",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    stats["skipped_alerts"].append(error_detail)
                    stats["alerts_skipped"] += 1
                    logger.info(f"Skipping alert {alert_id}: {reasoning}")

                else:
                    # HIGH PRIORITY: Track unknown action as error
                    error_detail = {
                        "alert_id": alert_id,
                        "db_alert_id": db_alert_id,
                        "reason": "unknown_action",
                        "message": f"Unknown action '{action}' from LLM",
                        "action": action,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    stats["skipped_alerts"].append(error_detail)
                    stats["alerts_skipped"] += 1
                    logger.error(
                        f"Unknown action '{action}' for alert {alert_id}, skipping"
                    )

            await session.commit()

            # Convert set to list for JSON serialization
            stats["groups_needing_triage"] = list(stats["groups_needing_triage"])

            logger.info(f"[Batch Worker] Batch processing complete:")
            logger.info(f"  - Total alerts: {stats['total_alerts']}")
            logger.info(f"  - New groups created: {stats['new_groups_created']}")
            logger.info(
                f"  - Alerts joined existing: {stats['alerts_joined_existing']}"
            )
            logger.info(f"  - Alerts skipped: {stats['alerts_skipped']}")
            logger.info(
                f"  - Groups needing triage: {len(stats['groups_needing_triage'])}"
            )

            # HIGH PRIORITY: Log detailed skip reasons for visibility
            if stats["skipped_alerts"]:
                logger.warning(f"  - Skipped alerts details:")
                for skip_detail in stats["skipped_alerts"]:
                    logger.warning(
                        f"    • Alert {skip_detail['alert_id']}: {skip_detail['reason']} - {skip_detail['message']}"
                    )

            return stats

    except Exception as e:
        # HIGH PRIORITY: Track exception details in stats
        error_detail = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        stats["errors"].append(error_detail)
        logger.exception(f"Error processing batch alerts for grouping")
        raise


async def run_batch_grouping_analysis(
    ungrouped_alerts: List[GroupingAlert], existing_groups: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Run LLM batch grouping analysis with comprehensive error handling."""
    logger.info(
        f"Running batch grouping analysis on {len(ungrouped_alerts)} alerts with {len(existing_groups)} existing groups"
    )

    # Create prompt
    prompt = create_batch_grouping_prompt(ungrouped_alerts, existing_groups)

    # Get LLM
    try:
        llm = await get_primary_llm_async()
    except Exception as e:
        logger.error(
            f"Failed to get primary LLM - BATCH GROUPING BLOCKED",
            extra={
                "error_id": "ERROR_LLM_INIT_FAILED",
                "alert_count": len(ungrouped_alerts),
                "error": str(e),
            },
        )
        # CRITICAL FIX: Raise exception instead of silently returning empty decisions
        # This ensures the job fails and can be retried, rather than silently skipping all alerts
        raise RuntimeError(f"LLM initialization failed: {e}") from e

    # CRITICAL: Wrap LLM invocation in try-catch
    try:
        response = await llm.ainvoke(prompt)
    except Exception as e:
        logger.error(
            f"LLM invocation failed during batch grouping - BATCH GROUPING BLOCKED",
            extra={
                "error_id": "ERROR_LLM_INVOCATION_FAILED",
                "error": str(e),
                "alert_count": len(ungrouped_alerts),
            },
        )
        # CRITICAL FIX: Raise exception instead of silently returning empty decisions
        raise RuntimeError(f"LLM invocation failed: {e}") from e

    # CRITICAL: Wrap JSON parsing in try-catch to prevent batch crashes
    try:
        content = response.content.strip()

        # Extract JSON from markdown code blocks if present
        content = extract_json_from_markdown(content)

        result = json.loads(content)

        # Validate response structure
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict, got {type(result).__name__}")

        if "decisions" not in result:
            raise ValueError("Missing 'decisions' key in LLM response")

        if not isinstance(result["decisions"], list):
            raise ValueError(
                f"Expected 'decisions' to be list, got {type(result['decisions']).__name__}"
            )

        logger.info(
            f"Grouping analysis complete: {len(result.get('decisions', []))} decisions returned"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse JSON from LLM response - BATCH GROUPING BLOCKED",
            extra={
                "error_id": "ERROR_LLM_JSON_PARSE_FAILED",
                "error": str(e),
                "response_preview": content[:500] if content else "empty",
                "alert_count": len(ungrouped_alerts),
            },
        )
        # CRITICAL FIX: Raise exception instead of silently returning empty decisions
        raise RuntimeError(f"Failed to parse LLM JSON response: {e}") from e

    except ValueError as e:
        logger.error(
            f"Invalid LLM response structure - BATCH GROUPING BLOCKED",
            extra={
                "error_id": "ERROR_LLM_RESPONSE_INVALID_STRUCTURE",
                "error": str(e),
                "alert_count": len(ungrouped_alerts),
            },
        )
        # CRITICAL FIX: Raise exception instead of silently returning empty decisions
        raise RuntimeError(f"Invalid LLM response structure: {e}") from e

    except Exception as e:
        logger.exception(
            f"Unexpected error parsing LLM response - BATCH GROUPING BLOCKED",
            extra={
                "error_id": "ERROR_LLM_RESPONSE_PARSE_UNEXPECTED",
                "alert_count": len(ungrouped_alerts),
            },
        )
        # CRITICAL FIX: Raise exception instead of silently returning empty decisions
        raise RuntimeError(f"Unexpected error parsing LLM response: {e}") from e

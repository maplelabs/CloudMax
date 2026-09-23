"""
Webhook Endpoints for External Integration.
"""

import hashlib
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_db_session
from src.server.models.api import Status
from src.server.models.db import AlertDBModel, EvaluationDBModel, TriageDBModel
from src.server.utilities.config import is_automatic_triage_enabled, is_alert_grouping_enabled
from src.triage.triage_job import enqueue_triage_job

logger = logging.getLogger(__name__)
router = APIRouter()


def map_severity_to_standard(severity: str) -> str:
    """
    Map various severity formats to standardized P1/P2/P3 format.

    Args:
        severity: Input severity string (case-insensitive)

    Returns:
        Standardized severity (P1, P2, or P3)
    """
    if not severity:
        return "P3"

    severity_lower = severity.lower().strip()

    # Mapping dictionary
    severity_mapping = {
        # P1 - Critical/High priority
        "p1": "P1",
        "critical": "P1",
        "high": "P1",
        "urgent": "P1",
        "severe": "P1",
        "emergency": "P1",

        # P2 - Warning/Medium priority
        "p2": "P2",
        "warning": "P2",
        "medium": "P2",
        "moderate": "P2",
        "warn": "P2",

        # P3 - Info/Low priority
        "p3": "P3",
        "info": "P3",
        "low": "P3",
        "minor": "P3",
        "informational": "P3",
        "notice": "P3"
    }

    return severity_mapping.get(severity_lower, "P3")


def hash_labels(labels: Dict[str, str]) -> str:
    """
    Create a short hash of labels dict (first 8 chars of sha256).
    """
    labels_str = json.dumps(labels, sort_keys=True)
    return hashlib.sha256(labels_str.encode()).hexdigest()[:8]


def webhook_result(inserted: int, updated: int, errors: int, alerts_enqueued_for_grouping: int, automatic_triage: bool) -> Dict[
    str, Any]:
    """
    Build the webhook response result dictionary.

    Args:
        inserted: Number of alerts inserted
        updated: Number of alerts updated
        errors: Number of errors encountered
        alerts_enqueued_for_grouping: Number of alerts enqueued for batch grouping (replaces triage_jobs_created)
        automatic_triage: Whether automatic triage is enabled

    Returns:
        Result dictionary with status and counts
    """
    result = {
        "status": "ok",
        "inserted": inserted,
        "updated": updated,
        "alerts_enqueued_for_grouping": alerts_enqueued_for_grouping,
        "automatic_triage": automatic_triage
    }

    if errors > 0:
        result["errors"] = errors
        result["status"] = "partial"

    logger.info(f"Webhook processed: {inserted} inserted, {updated} updated, {errors} errors, "
                f"{alerts_enqueued_for_grouping} alerts enqueued for grouping, automatic triage is {automatic_triage}")

    return result


@router.post("/alerts/grafana")
async def grafana_webhook(
        payload: Dict[str, Any],
        session: AsyncSession = Depends(get_db_session)
):
    """
    Ingest alerts from Grafana webhook.
    - For firing: always insert new alert row.
    - For resolved: mark all unresolved alerts with same external_id as resolved.
    """

    try:
        if "alerts" not in payload:
            logger.warning("Received payload without 'alerts' key")
            raise HTTPException(
                status_code=400, detail="Invalid payload: missing 'alerts' key")

        alerts = payload["alerts"]
        if not isinstance(alerts, list):
            logger.warning("'alerts' is not a list")
            raise HTTPException(
                status_code=400, detail="Invalid payload: 'alerts' must be a list")

        inserted, updated, errors = 0, 0, 0
        new_alerts_for_triage = []  # Track new alerts that need triage

        for alert in alerts:
            try:
                alertname = alert.get("labels", {}).get("alertname", "unknown")
                fingerprint = alert.get("fingerprint") or ""
                status = alert.get("status", "firing")
                labels = alert.get("labels", {})
                raw_severity = labels.get("severity")
                severity = map_severity_to_standard(raw_severity)
                alert_source = "grafana"

                # Build external_id = alertname-fingerprint-labelhash
                label_hash = hash_labels(labels)
                external_id = f"{alert_source}__{fingerprint}__{label_hash}"

                if status == "firing":
                    # Always insert a new alert
                    new_alert = AlertDBModel(
                        external_id=external_id,
                        payload=alert,
                        alert_source=alert_source,
                        alert_status=status,
                        severity=severity,
                        alert_name=alertname,
                    )
                    session.add(new_alert)
                    await session.flush()  # Flush to get the alert ID

                    # Add to list for triage processing
                    new_alerts_for_triage.append(new_alert)
                    inserted += 1
                    logger.debug(f"Inserted new alert: {external_id}")

                elif status == "resolved":
                    # Update all firing alerts with same external_id
                    stmt = (
                        select(AlertDBModel)
                        .where(AlertDBModel.external_id == external_id)
                        .where(AlertDBModel.alert_status == "firing")
                    )
                    result = await session.execute(stmt)
                    firing_alerts = result.scalars().all()

                    if firing_alerts:
                        for existing_alert in firing_alerts:
                            existing_alert.alert_status = "resolved"
                            existing_alert.payload = alert
                            existing_alert.ends_at = alert.get("endsAt")
                            updated += 1
                            logger.debug(
                                f"Resolved alert: {existing_alert.external_id}")
                    else:
                        logger.warning(
                            f"No firing alerts found to resolve for {external_id}")

            except Exception as e:
                logger.exception(f"Error processing individual alert")
                errors += 1
                continue

        # Commit all DB changes
        await session.commit()

        # Check if alert grouping is enabled (from database config)
        grouping_enabled = await is_alert_grouping_enabled()
        automatic_triage = await is_automatic_triage_enabled()
        alerts_enqueued_for_grouping = 0

        if grouping_enabled:
            # ALERT GROUPING ENABLED: Leave alerts ungrouped for Worker 1 to process
            # Worker 1 (scheduled every 5 min) will fetch all ungrouped alerts from DB
            alerts_enqueued_for_grouping = inserted
            logger.info(f"Inserted {inserted} new alerts (group_id=NULL)")
            logger.info(f"Alert grouping ENABLED - Worker 1 will process ungrouped alerts every 5 minutes")
        else:
            # ALERT GROUPING DISABLED: Enqueue individual triage jobs immediately (old behavior)
            logger.info(f"Alert grouping DISABLED - Enqueueing individual triage jobs for {len(new_alerts_for_triage)} alerts")

            if automatic_triage and new_alerts_for_triage:
                import uuid
                from sqlalchemy import select

                for alert in new_alerts_for_triage:
                    try:
                        # Generate thread_id for this triage
                        thread_id = str(uuid.uuid4())

                        # Create evaluation record BEFORE triage record (required by triage job)
                        existing_eval = await session.scalar(
                            select(EvaluationDBModel).where(EvaluationDBModel.alert_id == alert.id)
                        )

                        if not existing_eval:
                            new_evaluation = EvaluationDBModel(
                                alert_id=alert.id,
                                group_id=None,  # Standalone alert
                                status=Status.PENDING
                            )
                            session.add(new_evaluation)
                            logger.info(f"Created evaluation record for alert {alert.id}")

                        # Create triage record
                        new_triage = TriageDBModel(
                            alert_id=alert.id,
                            status=Status.QUEUED,
                            thread_id=thread_id
                        )
                        session.add(new_triage)

                        # Flush to get IDs before enqueueing job
                        await session.flush()

                        # Enqueue individual triage job
                        job_id = enqueue_triage_job(
                            alert_id=alert.id,
                            triage_id=thread_id,
                            queue_name="high_priority_triages"
                        )

                        # Update triage record with job_id
                        new_triage.job_id = job_id

                        logger.info(f"Enqueued individual triage job for alert {alert.id}: job_id={job_id}, thread_id={thread_id}")
                    except Exception as e:
                        logger.error(f"Failed to enqueue triage job for alert {alert.id}: {e}")
                        await session.rollback()
                        raise

                # Commit all triage records
                await session.commit()
                logger.info(f"Successfully enqueued {len(new_alerts_for_triage)} individual triage jobs")
            else:
                if not automatic_triage:
                    logger.info(f"Automatic triage DISABLED - No triage jobs enqueued")
                else:
                    logger.info(f"No new alerts to triage")

        return webhook_result(
            inserted, updated, errors, alerts_enqueued_for_grouping, automatic_triage
        )

    except HTTPException:
        raise

    except SQLAlchemyError:
        logger.exception(f"Database error in webhook")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred")

    except Exception:
        logger.exception("Unexpected error in webhook")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

"""
Ungrouped Alert Retry Job (Job 2)

Finds ungrouped alerts and either retries grouping (recent alerts) or triages as standalone (old alerts).
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import AlertDBModel, TriageDBModel, EvaluationDBModel
from src.server.models.api.enums import Status
from src.alert_grouping.services import process_batch_alerts_for_grouping_async

logger = logging.getLogger(__name__)


async def retry_ungrouped_alerts_async():
    """
    Find ungrouped alerts and either retry grouping (recent) or triage as standalone (old).
    """
    logger.info("[Job 2] UNGROUPED ALERT RETRY JOB STARTED")

    try:
        # Check if alert grouping is still enabled (flag may have changed since scheduling)
        from src.server.utilities.config import is_alert_grouping_enabled

        if not await is_alert_grouping_enabled():
            logger.info(
                "[Job 2] UNGROUPED ALERT RETRY JOB Skipped - alert_grouping_enabled=false in database"
            )
            return

        from src.server.utilities.grouping_config import get_grouping_config_async

        config = await get_grouping_config_async()

        standalone_threshold = datetime.now(timezone.utc) - timedelta(
            minutes=config.standalone_alert_timeout_minutes
        )

        async with async_db_session() as session:
            lookback_time = datetime.now(timezone.utc) - timedelta(
                hours=config.ungrouped_alerts_lookback_hours
            )

            stmt = (
                select(AlertDBModel)
                .outerjoin(TriageDBModel, AlertDBModel.id == TriageDBModel.alert_id)
                .where(
                    and_(
                        AlertDBModel.group_id.is_(None),
                        AlertDBModel.created_at >= lookback_time,
                        TriageDBModel.id.is_(None),
                    )
                )
                .order_by(AlertDBModel.created_at.asc())
                .limit(config.max_alerts_per_batch)
            )

            result = await session.execute(stmt)
            ungrouped_alerts = result.scalars().all()

            if not ungrouped_alerts:
                logger.info("No ungrouped alerts found")
                return

            # Separate alerts into two categories
            recent_alerts = []  # < 30 min old - retry grouping
            standalone_alerts = []  # ≥ 30 min old - triage as standalone

            for alert in ungrouped_alerts:
                if alert.created_at < standalone_threshold:
                    standalone_alerts.append(alert)
                else:
                    recent_alerts.append(alert)

            logger.info(f"Found {len(ungrouped_alerts)} ungrouped alerts:")
            logger.info(
                f"  - {len(recent_alerts)} recent alerts (< {config.standalone_alert_timeout_minutes} min) - will retry grouping"
            )
            logger.info(
                f"  - {len(standalone_alerts)} old alerts (≥ {config.standalone_alert_timeout_minutes} min) - will triage as standalone"
            )

            # Process recent alerts for grouping
            if recent_alerts:
                alert_ids = [alert.id for alert in recent_alerts]
                logger.info(
                    f"Retrying grouping for {len(alert_ids)} recent alerts: {alert_ids}"
                )
                stats = await process_batch_alerts_for_grouping_async(alert_ids)
                logger.info(f"Batch grouping stats: {stats}")

            # Process standalone alerts
            if standalone_alerts:
                await process_standalone_alerts(session, standalone_alerts, config)

        logger.info("[Job 2] UNGROUPED ALERT RETRY JOB COMPLETED")

    except Exception:
        logger.exception("Error in ungrouped alert retry job")
        raise


async def process_standalone_alerts(session, standalone_alerts, config):
    """
    Enqueue old ungrouped alerts for direct triage (without creating groups).

    Args:
        session: Database session
        standalone_alerts: List of alerts that are old enough to be triaged standalone
        config: Alert grouping configuration
    """
    logger.info(
        f"Processing {len(standalone_alerts)} standalone alerts for direct triage..."
    )

    # CRITICAL FIX: Check if any triage (group OR standalone) is already in progress
    # This prevents parallel triaging which causes rate limit errors
    from src.server.models.db import AlertGroupDBModel

    # Check for in-progress group triages
    in_progress_groups = await session.execute(
        select(AlertGroupDBModel).where(
            AlertGroupDBModel.status == "active",
            AlertGroupDBModel.triage_status == "in_progress",
        )
    )
    in_progress_group_list = in_progress_groups.scalars().all()

    # Check for in-progress standalone alert triages
    in_progress_triages = await session.execute(
        select(TriageDBModel).where(
            TriageDBModel.status.in_([Status.PROCESSING, Status.QUEUED])
        )
    )
    in_progress_triage_list = in_progress_triages.scalars().all()

    if in_progress_group_list or in_progress_triage_list:
        logger.info(f"Skipping standalone alert triage enqueue:")
        if in_progress_group_list:
            logger.info(
                f"   - {len(in_progress_group_list)} group(s) already in progress (IDs: {[g.id for g in in_progress_group_list]})"
            )
        if in_progress_triage_list:
            logger.info(
                f"   - {len(in_progress_triage_list)} standalone alert(s) being triaged (Alert IDs: {[t.alert_id for t in in_progress_triage_list]})"
            )
        logger.info(
            "   Waiting for current triage to complete before starting next one"
        )
        return

    # CRITICAL FIX: Only enqueue ONE standalone alert at a time to avoid rate limit errors
    # The scheduler runs every 5 minutes, so the next alert will be picked up
    # after the current one completes
    if not standalone_alerts:
        logger.info("No standalone alerts to process")
        return

    alert = standalone_alerts[0]  # Take the oldest standalone alert

    try:
        # Check if triage already exists and is in progress
        latest_triage = await session.scalar(
            select(TriageDBModel)
            .where(TriageDBModel.alert_id == alert.id)
            .order_by(TriageDBModel.created_at.desc())
        )

        # Skip if triage is already in progress
        if latest_triage and latest_triage.status in [Status.QUEUED, Status.PROCESSING]:
            logger.info(
                f"Skipping alert {alert.id} - triage already in progress (status: {latest_triage.status})"
            )
            return

        # Generate thread_id for triage
        thread_id = str(uuid.uuid4())

        # CRITICAL FIX: Create evaluation record BEFORE creating triage record
        # The triage job expects an evaluation record to exist
        existing_eval = await session.scalar(
            select(EvaluationDBModel).where(EvaluationDBModel.alert_id == alert.id)
        )

        if not existing_eval:
            new_evaluation = EvaluationDBModel(
                alert_id=alert.id,
                group_id=None,  # Standalone alert, not part of a group
                status=Status.PENDING,
            )
            session.add(new_evaluation)
            logger.info(f"Created evaluation record for standalone alert {alert.id}")

        # CRITICAL FIX: Create triage record but DON'T commit yet
        # We need to enqueue the job FIRST, then commit
        # This prevents the alert from being stuck if enqueue fails
        new_triage = TriageDBModel(
            alert_id=alert.id, status=Status.QUEUED, thread_id=thread_id
        )
        session.add(new_triage)

        # ENQUEUE JOB FIRST (before committing to database)
        # If this fails, the rollback will prevent the triage record from being created
        from src.triage.triage_job import enqueue_triage_job

        job_id = enqueue_triage_job(
            alert_id=alert.id,
            triage_id=thread_id,
            queue_name="high_priority_triages",  # Use high priority for standalone alerts
        )

        # ONLY COMMIT IF ENQUEUE SUCCEEDED
        # This ensures the triage record and job are created atomically
        new_triage.job_id = job_id
        await session.commit()

        logger.info(
            f"Created STANDALONE triage record for alert {alert.id} (thread_id={thread_id})"
        )
        logger.info(
            f"Enqueued standalone alert triage job {job_id} for alert {alert.id}"
        )
        logger.info(f"   Remaining standalone alerts: {len(standalone_alerts) - 1}")

    except Exception as e:
        logger.exception(f"Failed to triage standalone alert {alert.id}: {e}")
        await session.rollback()
        # Alert stays ungrouped and will be retried in the next run


def run_ungrouped_retry_worker():
    """
    Job 2: Synchronous wrapper for the async ungrouped retry job.
    This is called by RQ scheduler every 5 minutes.

    Note: This job finds ungrouped alerts and either retries grouping or triages standalone alerts.
    """
    logger.info("[JOB 2: UNGROUPED RETRY] Triggered by scheduler")

    try:
        # Run the async job
        asyncio.run(retry_ungrouped_alerts_async())

        logger.info("[JOB 2: UNGROUPED RETRY] Completed successfully")

    except Exception:
        logger.exception("[JOB 2: UNGROUPED RETRY] Failed with exception")
        raise


if __name__ == "__main__":
    # For manual testing
    run_ungrouped_retry_worker()

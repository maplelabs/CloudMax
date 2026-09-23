"""
Batch Alert Grouping Job (Job 1)

Runs every 5 minutes to find ungrouped alerts and process them in a single batch.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import AlertDBModel, TriageDBModel
from src.alert_grouping.services import process_batch_alerts_for_grouping_async

logger = logging.getLogger(__name__)


async def batch_grouping_from_db_async():
    """
    Find ungrouped alerts and process them as a batch.
    """
    logger.info("[JOB 1: BATCH GROUPING] Started")

    try:
        # Check if alert grouping is still enabled (flag may have changed since scheduling)
        from src.server.utilities.config import is_alert_grouping_enabled

        if not await is_alert_grouping_enabled():
            logger.info(
                "[JOB 1: BATCH GROUPING] Skipped - alert_grouping_enabled=false in database"
            )
            return {}

        from src.server.utilities.grouping_config import get_grouping_config_async

        config = await get_grouping_config_async()

        async with async_db_session() as session:
            lookback_time = datetime.now(timezone.utc) - timedelta(
                hours=config.ungrouped_alerts_lookback_hours
            )

            # Exclude alerts that already have triage records
            triage_alert_ids = select(TriageDBModel.alert_id)

            stmt = (
                select(AlertDBModel)
                .where(
                    and_(
                        AlertDBModel.group_id.is_(None),
                        AlertDBModel.created_at >= lookback_time,
                        ~AlertDBModel.id.in_(triage_alert_ids),
                    )
                )
                .order_by(AlertDBModel.created_at.asc())
                .limit(config.max_alerts_per_batch)
                .with_for_update(skip_locked=True)
            )

            result = await session.execute(stmt)
            ungrouped_alerts = result.scalars().all()

            if not ungrouped_alerts:
                logger.info("[JOB 1: BATCH GROUPING] No ungrouped alerts found")
                return {}

            alert_ids = [alert.id for alert in ungrouped_alerts]
            logger.info(
                f"[JOB 1: BATCH GROUPING] Found {len(alert_ids)} ungrouped alerts: {alert_ids}"
            )

        # Process all alerts as a batch
        stats = await process_batch_alerts_for_grouping_async(alert_ids)

        logger.info(f"[JOB 1: BATCH GROUPING] Stats: {stats}")

        # NOTE: Group triage is handled by the group triage scheduler (Job 3)
        # Groups are marked as triage_status='pending' during creation
        # and will be picked up automatically by the triage scheduler
        groups_needing_triage = stats.get("groups_needing_triage", [])
        if groups_needing_triage:
            logger.info(
                f"[JOB 1: BATCH GROUPING] Created {len(groups_needing_triage)} new groups that will be triaged by the scheduler: {groups_needing_triage}"
            )

        logger.info("[JOB 1: BATCH GROUPING] Completed")

        return stats

    except Exception:
        logger.exception("[JOB 1: BATCH GROUPING] Error occurred")
        raise


def run_batch_grouping_worker():
    """
    Job 1: Synchronous wrapper for the async batch grouping job.
    This is called by RQ scheduler every 5 minutes.

    Note: This job queries database for ungrouped alerts and processes them as a batch.
    """
    logger.info("[JOB 1: BATCH GROUPING] Triggered by scheduler")

    try:
        # Run the async job
        asyncio.run(batch_grouping_from_db_async())

        logger.info("[JOB 1: BATCH GROUPING] Completed successfully")

    except Exception:
        logger.exception("[JOB 1: BATCH GROUPING] Failed with exception")
        raise


if __name__ == "__main__":
    # For manual testing
    run_batch_grouping_worker()

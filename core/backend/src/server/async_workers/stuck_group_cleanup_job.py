"""
Stuck Group Cleanup Job

Runs every hour to reset groups stuck in 'in_progress' status for more than 2 hours.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import AlertGroupDBModel

logger = logging.getLogger(__name__)


async def cleanup_stuck_groups_async():
    """
    Find and reset groups stuck in 'in_progress' for more than 2 hours.
    """
    logger.info("[STUCK GROUP CLEANUP] Starting cleanup job")

    stuck_threshold = datetime.now(timezone.utc) - timedelta(hours=2)

    try:
        async with async_db_session() as session:
            stmt = select(AlertGroupDBModel).where(
                AlertGroupDBModel.triage_status == "in_progress",
                AlertGroupDBModel.updated_at < stuck_threshold,
            )

            result = await session.execute(stmt)
            stuck_groups = result.scalars().all()

            if not stuck_groups:
                logger.info("No stuck groups found")
                return 0

            logger.warning(f"Found {len(stuck_groups)} stuck group(s)")

            for group in stuck_groups:
                logger.error(
                    f"Found stuck group {group.id} - resetting to pending",
                    extra={
                        "error_id": "ERROR_STUCK_GROUP_DETECTED",
                        "group_id": group.id,
                        "group_name": group.group_name,
                        "stuck_since": group.updated_at.isoformat(),
                        "hours_stuck": (
                            datetime.now(timezone.utc) - group.updated_at
                        ).total_seconds()
                        / 3600,
                    },
                )

                group.triage_status = "pending"
                group.error_message = f"Triage timed out (stuck for >2 hours) - will retry. Last update: {group.updated_at}"
                group.thread_id = None

            await session.commit()

            logger.info(f"Reset {len(stuck_groups)} stuck group(s) to pending status")

            return len(stuck_groups)

    except Exception as e:
        logger.exception(f"Failed to cleanup stuck groups: {e}")
        raise


def run_stuck_group_cleanup_worker():
    """
    Synchronous wrapper for the async stuck group cleanup job.
    This is called by RQ scheduler every hour.
    """
    logger.info("[STUCK GROUP CLEANUP] Triggered by scheduler")

    try:
        # Run the async cleanup
        reset_count = asyncio.run(cleanup_stuck_groups_async())
        logger.info(
            f"[STUCK GROUP CLEANUP] Completed successfully - reset {reset_count} group(s)"
        )
        return reset_count

    except Exception:
        logger.exception("[STUCK GROUP CLEANUP] Failed with exception")
        raise


if __name__ == "__main__":
    # For manual testing
    run_stuck_group_cleanup_worker()

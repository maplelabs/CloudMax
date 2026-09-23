"""
Startup cleanup script to remove old duplicate triages from the database.

This script runs once when the backend service starts, before the FastAPI server starts.
It finds all alerts with multiple triage records and enqueues a cleanup job to delete
the old triages, keeping only the latest one per alert.

Purpose:
- For already deployed systems that have accumulated duplicate triages
- One-time cleanup of existing old data
- Ensures database is clean before normal operations begin

When it runs:
- After database migrations complete
- Before FastAPI server starts
- Automatically from entrypoint.sh (MODE=backend)
"""

import asyncio
import logging
import sys

from sqlalchemy import select, func

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def find_duplicate_triages():
    """
    Find all alerts that have multiple triage records.

    Returns:
        list: List of old triage IDs to delete (keeps latest triage per alert)
    """
    from src.server.apis_v1.dependencies import async_db_session
    from src.server.models.db import TriageDBModel

    old_triage_ids = []

    try:
        async with async_db_session() as session:
            # Find all alert_ids that have more than 1 triage
            stmt = (
                select(TriageDBModel.alert_id, func.count(TriageDBModel.id).label('count'))
                .group_by(TriageDBModel.alert_id)
                .having(func.count(TriageDBModel.id) > 1)
            )

            result = await session.execute(stmt)
            alerts_with_duplicates = result.fetchall()

            if not alerts_with_duplicates:
                logger.info("✅ No duplicate triages found. Database is clean!")
                return []

            logger.info(f"Found {len(alerts_with_duplicates)} alert(s) with multiple triages")

            # For each alert with duplicates, get the old triage IDs
            for alert_id, count in alerts_with_duplicates:
                # Get all triages for this alert, sorted by created_at (newest first)
                triages_stmt = (
                    select(TriageDBModel)
                    .where(TriageDBModel.alert_id == alert_id)
                    .order_by(TriageDBModel.created_at.desc())
                )

                triages_result = await session.execute(triages_stmt)
                triages = list(triages_result.scalars().all())

                if len(triages) > 1:
                    # Keep the first one (latest), delete the rest
                    latest_triage = triages[0]
                    old_triages = triages[1:]

                    old_ids = [t.id for t in old_triages]
                    old_triage_ids.extend(old_ids)

                    logger.info(f"  Alert {alert_id}: {len(triages)} triages found, "
                                f"keeping latest (ID: {latest_triage.id}), "
                                f"marking {len(old_ids)} for deletion")

            logger.info(f"Total old triages to delete: {len(old_triage_ids)}")

    except Exception as e:
        logger.error(f"Error finding duplicate triages: {e}")
        logger.exception("Full error details:")
        return []

    return old_triage_ids


def schedule_periodic_jobs():
    """
    Schedule periodic background jobs (Confluence sync, etc.)

    This is called once during job-scheduler startup to register
    recurring jobs with RQ Scheduler.
    """
    logger.info("PERIODIC JOBS: Scheduling recurring background jobs...")

    try:
        from src.server.async_workers.confluence_sync_job import schedule_daily_confluence_sync

        # Schedule daily Confluence sync
        job_id = schedule_daily_confluence_sync()
        logger.info(f"Scheduled daily Confluence sync job: {job_id}")
        logger.info("   Schedule: Daily at 2:00 AM (cron: 0 2 * * *)")

    except Exception as e:
        logger.error(f"Error scheduling periodic jobs: {e}")
        logger.exception("Full error details:")
        logger.warning("  Periodic job scheduling failed, but scheduler will continue...")

    finally:
        logger.info("PERIODIC JOBS: Scheduling complete")


async def run_startup_cleanup():
    """
    Main function to run startup cleanup.
    
    Finds duplicate triages and enqueues a cleanup job to delete them.
    """
    logger.info("STARTUP CLEANUP: Checking for duplicate triages...")

    try:
        # Find all old triage IDs to delete
        old_triage_ids = await find_duplicate_triages()

        if not old_triage_ids:
            logger.info(" No cleanup needed. Startup cleanup complete.")
            return

        # Enqueue cleanup job
        logger.info(f"Enqueueing cleanup job for {len(old_triage_ids)} old triage(s)...")

        from src.server.async_workers.cleanup_job import enqueue_cleanup_job

        # Enqueue without dependency (no triage job to wait for)
        cleanup_job_id = enqueue_cleanup_job(old_triage_ids, depends_on_job_id=None)

        if cleanup_job_id:
            logger.info(f"Cleanup job enqueued successfully: {cleanup_job_id}")
            logger.info(f"   The cleanup job will run in the background (low_priority_triages queue)")
            logger.info(f"   Old triages and their checkpoints will be deleted automatically")
        else:
            logger.warning(" Cleanup job was not enqueued (no old triages to clean)")

    except Exception as e:
        logger.error(f"Error during startup cleanup: {e}")
        logger.exception("Full error details:")
        logger.warning("  Startup cleanup failed, but backend will continue starting...")

    finally:
        logger.info("STARTUP CLEANUP: Complete")


def main():
    """
    Entry point for the startup cleanup script.
    Also schedules periodic jobs when running as job-scheduler.
    """
    try:
        # Schedule periodic jobs (Confluence sync, etc.)
        # This is idempotent - RQ Scheduler will not duplicate jobs
        schedule_periodic_jobs()

        # Run the async cleanup function
        asyncio.run(run_startup_cleanup())
        sys.exit(0)  # Success
    except Exception as e:
        logger.error(f"Fatal error in startup cleanup: {e}")
        logger.exception("Full error details:")
        # Don't fail the startup - just log and continue
        sys.exit(0)  # Exit successfully even if cleanup fails


if __name__ == "__main__":
    main()

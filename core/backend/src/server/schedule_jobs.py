"""
Schedule periodic jobs with RQ Scheduler.

This script registers all periodic/scheduled jobs that should run in the background.
It runs once when the job-scheduler service starts.

SINGLE WORKER Architecture:
- All 3 jobs below are processed by the SINGLE 'grouper' worker
- The worker listens to both RQ_GROUPING_QUEUE_NAME and RQ_TRIAGE_QUEUE_NAME

Worker 1: Batch Grouping (Scheduled - configurable interval)
   - Queries database for ungrouped alerts
   - Processes them as a batch using LLM
   - Creates/updates groups based on LLM decisions

Worker 2: Ungrouped Retry (Scheduled - configurable interval)
   - Finds alerts that are still ungrouped (group_id IS NULL)
   - Re-processes them to allow grouping with newly created groups

Worker 3: Group Triage Scheduler (Scheduled - configurable interval)
   - Fetches groups with triage_status='pending'
   - Enqueues individual triage jobs for each group
   - Each triage job performs RCA using LangGraph orchestrator

Environment Variables:
- GROUP_TRIAGE_ENABLED: Enable/disable Worker 3 (default: true)
- RQ_GROUPING_QUEUE_NAME: Queue for grouping jobs (default: alert_grouping)
- RQ_TRIAGE_QUEUE_NAME: Queue for triage jobs (default: group_triage)

Configuration:
- alert_grouping_enabled: Enable/disable Workers 1 & 2 (database-driven, default: true)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from src.server.utilities import get_scheduler
from src.server.utilities.config import is_alert_grouping_enabled
from src.server.utilities.grouping_config import get_grouping_config_async

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def is_group_triage_enabled() -> bool:
    """Check if group triage is enabled via environment variable."""
    return os.getenv("GROUP_TRIAGE_ENABLED", "true").lower() in ("true", "1", "yes")


def get_grouping_queue_name() -> str:
    """Get the grouping queue name from environment."""
    return os.getenv("RQ_GROUPING_QUEUE_NAME", "alert_grouping")


def get_triage_queue_name() -> str:
    """Get the triage queue name from environment."""
    return os.getenv("RQ_TRIAGE_QUEUE_NAME", "group_triage")


async def schedule_batch_grouping_job():
    """
    Worker 1: Schedule the batch grouping job to run at configured interval.
    This job queries database for ungrouped alerts and processes them as a batch.
    """
    # Check if alert grouping is enabled (from database)
    if not await is_alert_grouping_enabled():
        logger.info(
            "Worker 1 (Batch Grouping) DISABLED - alert_grouping_enabled=false in database"
        )
        return None

    try:
        from src.server.async_workers.batch_grouping_job import (
            run_batch_grouping_worker,
        )

        # Load configuration
        config = await get_grouping_config_async()

        # Get scheduler for the configured grouping queue
        queue_name = get_grouping_queue_name()
        scheduler = get_scheduler(queue_name)

        # Cancel any existing scheduled jobs for this function
        # This prevents duplicate jobs if the scheduler restarts
        for job in scheduler.get_jobs():
            if (
                job.func_name
                == "src.server.async_workers.batch_grouping_job.run_batch_grouping_worker"
            ):
                logger.info(f"Canceling existing batch grouping job: {job.id}")
                scheduler.cancel(job)

        # Schedule the job using configured interval
        from src.alert_grouping.services import BATCH_GROUPING_TIMEOUT_SEC

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),  # Start immediately
            func=run_batch_grouping_worker,
            interval=config.batch_grouping_interval_sec,
            repeat=None,  # Repeat indefinitely
            timeout=f"{BATCH_GROUPING_TIMEOUT_SEC}s",
        )

        logger.info(f"Scheduled Worker 1 (Batch Grouping): {job.id}")
        logger.info(f"   - Runs every {config.batch_grouping_interval_sec} seconds")
        logger.info(f"   - Queue: {queue_name}")
        logger.info(f"   - Timeout: {BATCH_GROUPING_TIMEOUT_SEC} seconds")

        return job.id

    except Exception:
        logger.exception("Failed to schedule batch grouping job")
        raise


async def schedule_ungrouped_retry_job():
    """
    Worker 2: Schedule the ungrouped alert retry job to run at configured interval.
    This job finds ungrouped alerts and re-enqueues them to Redis.
    """
    # Check if alert grouping is enabled (from database)
    if not await is_alert_grouping_enabled():
        logger.info(
            "Worker 2 (Ungrouped Retry) DISABLED - alert_grouping_enabled=false in database"
        )
        return None

    try:
        from src.server.async_workers.ungrouped_retry_job import (
            run_ungrouped_retry_worker,
        )

        # Load configuration
        config = await get_grouping_config_async()

        # Get scheduler for the configured grouping queue
        queue_name = get_grouping_queue_name()
        scheduler = get_scheduler(queue_name)

        # Cancel any existing scheduled jobs for this function
        # This prevents duplicate jobs if the scheduler restarts
        for job in scheduler.get_jobs():
            if (
                job.func_name
                == "src.server.async_workers.ungrouped_retry_job.run_ungrouped_retry_worker"
            ):
                logger.info(f"Canceling existing ungrouped retry job: {job.id}")
                scheduler.cancel(job)

        # Schedule the job using configured interval
        from src.alert_grouping.services import UNGROUPED_RETRY_TIMEOUT_SEC

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),  # Start immediately
            func=run_ungrouped_retry_worker,
            interval=config.ungrouped_retry_interval_sec,
            repeat=None,  # Repeat indefinitely
            timeout=f"{UNGROUPED_RETRY_TIMEOUT_SEC}s",
        )

        logger.info(f"Scheduled Worker 2 (Ungrouped Retry): {job.id}")
        logger.info(f"   - Runs every {config.ungrouped_retry_interval_sec} seconds")
        logger.info(f"   - Queue: {queue_name}")
        logger.info(f"   - Timeout: {UNGROUPED_RETRY_TIMEOUT_SEC} seconds")

        return job.id

    except Exception:
        logger.exception("Failed to schedule ungrouped retry job")
        raise


async def schedule_group_triage_job():
    """
    Worker 3: Schedule the group triage scheduler to run at configured interval.
    The scheduler finds pending groups and enqueues them as separate jobs.
    Each enqueued job will be processed by the grouper worker.
    """
    # Check if group triage is enabled
    if not is_group_triage_enabled():
        logger.info("Worker 3 (Group Triage) DISABLED via GROUP_TRIAGE_ENABLED=false")
        return None

    try:
        from src.server.async_workers.group_triage_job import run_group_triage_scheduler

        # Load configuration
        config = await get_grouping_config_async()

        # Get scheduler for the configured triage queue
        queue_name = get_triage_queue_name()
        scheduler = get_scheduler(queue_name)

        # Cancel any existing scheduled jobs for this function
        # This prevents duplicate jobs if the scheduler restarts
        for job in scheduler.get_jobs():
            if "group_triage" in job.func_name.lower():
                logger.info(f"Canceling existing group triage scheduler job: {job.id}")
                scheduler.cancel(job)

        # Schedule the job using configured interval
        # This scheduler job just enqueues groups, so it should be fast (no timeout needed)
        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),  # Start immediately
            func=run_group_triage_scheduler,
            interval=config.group_triage_interval_sec,
            repeat=None,  # Repeat indefinitely
        )

        logger.info(f"Scheduled Worker 3 (Group Triage Scheduler): {job.id}")
        logger.info(f"   - Runs every {config.group_triage_interval_sec} seconds")
        logger.info(f"   - Queue: {queue_name}")
        logger.info(f"   - No timeout (scheduler just enqueues groups)")
        logger.info(f"   - Enqueued triage jobs run with job_timeout=-1 (no timeout)")

        return job.id

    except Exception:
        logger.exception("Failed to schedule group triage job")
        raise


async def schedule_stuck_group_cleanup_job():
    """
    Worker 4: Schedule the stuck group cleanup job to run every hour.
    This job finds groups stuck in 'in_progress' for >2 hours and resets them.
    """
    try:
        from src.server.async_workers.stuck_group_cleanup_job import (
            run_stuck_group_cleanup_worker,
        )

        # Get scheduler for the triage queue (cleanup is related to triage)
        queue_name = get_triage_queue_name()
        scheduler = get_scheduler(queue_name)

        # Cancel any existing scheduled jobs for this function
        for job in scheduler.get_jobs():
            if "stuck_group_cleanup" in job.func_name.lower():
                logger.info(f"Canceling existing stuck group cleanup job: {job.id}")
                scheduler.cancel(job)

        # Schedule to run every hour
        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),  # Start immediately
            func=run_stuck_group_cleanup_worker,
            interval=3600,  # Run every hour
            repeat=None,  # Repeat indefinitely
            timeout="10m",  # 10 minutes timeout
        )

        logger.info(f"Scheduled Worker 4 (Stuck Group Cleanup): {job.id}")
        logger.info(f"   - Runs every 3600 seconds (1 hour)")
        logger.info(f"   - Queue: {queue_name}")
        logger.info(f"   - Timeout: 10 minutes")

        return job.id

    except Exception:
        logger.exception("Failed to schedule stuck group cleanup job")
        raise


async def main_async():
    """
    Main async function to schedule all periodic jobs.

    4-Job Architecture:
    - Job 1: Batch Grouping (periodic, configurable interval) - Queries DB for ungrouped alerts, processes as batch
    - Job 2: Ungrouped Retry + Standalone Triage (periodic, configurable interval) - Retries recent alerts, triages old ones
    - Job 3: Group Triage (periodic, configurable interval) - Triages pending groups
    - Job 4: Stuck Group Cleanup (periodic, every hour) - Resets groups stuck in 'in_progress' for >2 hours

            RESILIENT SCHEDULING: Jobs are scheduled independently.
            If one job fails to schedule, others will still be scheduled.
    """
    logger.info("=" * 80)
    logger.info("SCHEDULING PERIODIC JOBS (4-Job Architecture)")
    logger.info("=" * 80)

    scheduled_jobs = []
    failed_jobs = []

    # Define all jobs to schedule
    jobs_to_schedule = [
        ("Job 1 (Batch Grouping)", schedule_batch_grouping_job),
        ("Job 2 (Ungrouped Retry + Standalone Triage)", schedule_ungrouped_retry_job),
        ("Job 3 (Group Triage Scheduler)", schedule_group_triage_job),
        ("Job 4 (Stuck Group Cleanup)", schedule_stuck_group_cleanup_job),
    ]

    # Schedule each job independently
    for job_name, schedule_func in jobs_to_schedule:
        logger.info("")
        logger.info(f"Scheduling {job_name}...")
        try:
            job_id = await schedule_func()
            if job_id:
                scheduled_jobs.append((job_name, job_id))
                logger.info(f"{job_name}: {job_id}")
            else:
                logger.info(f"{job_name}: DISABLED")
        except Exception as e:
            logger.error(f"{job_name} failed: {e}")
            logger.exception(f"Full error for {job_name}:")
            failed_jobs.append((job_name, str(e)))

    # Print summary
    logger.info("")
    logger.info("=" * 80)
    if scheduled_jobs and not failed_jobs:
        logger.info("ALL PERIODIC JOBS SCHEDULED SUCCESSFULLY")
    elif scheduled_jobs and failed_jobs:
        logger.warning("PARTIAL SUCCESS: SOME JOBS SCHEDULED, SOME FAILED")
    else:
        logger.error("CRITICAL: NO JOBS SCHEDULED")
    logger.info("=" * 80)

    # Print scheduled jobs
    if scheduled_jobs:
        logger.info("SCHEDULED JOBS:")
        for job_name, job_id in scheduled_jobs:
            logger.info(f"  {job_name}: {job_id}")

    # Print failed jobs
    if failed_jobs:
        logger.error("FAILED JOBS:")
        for job_name, error in failed_jobs:
            logger.error(f"  {job_name}: {error}")

    logger.info("")
    logger.info("Intervals are configurable via alert_grouping_config")
    logger.info("=" * 80)

    # Exit with partial success if at least one job scheduled
    if scheduled_jobs:
        sys.exit(0)  # Success (at least some jobs scheduled)
    else:
        logger.error("CRITICAL: No jobs scheduled - exiting with failure")
        sys.exit(1)  # Failure (no jobs scheduled)


def main():
    """Wrapper to run async main function"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

"""
Cleanup job for deleting old triages and their checkpoints.

This job runs in the low_priority_triages queue and deletes:
1. Old triage records from the triages table
2. Checkpoints for those triages from the checkpoint database

This job is triggered when a new manual triage is created for an existing alert.
"""
import asyncio
import logging
import os
import time

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from rq import get_current_job
from sqlalchemy import delete

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.db import TriageDBModel
from src.server.utilities import get_queue

logger = logging.getLogger(__name__)


async def cleanup_triages_and_checkpoints(triage_ids: list) -> dict:
    """
    Clean up triages and their checkpoints.

    Args:
        triage_ids: List of triage IDs to delete

    Returns:
        Dictionary with cleanup statistics
    """
    stats = {
        "triages_deleted": 0,
        "checkpoints_deleted": 0,
        "errors": 0
    }

    if not triage_ids:
        logger.info("No triage IDs to clean up")
        return stats

    logger.info(f"Starting cleanup for {len(triage_ids)} triage(s)")

    try:
        # Step 1: Get thread_ids for these triages before deleting them
        thread_ids = []
        async with async_db_session() as session:
            try:
                # Get thread_ids for the triages we're about to delete
                from sqlalchemy import select
                result = await session.execute(
                    select(TriageDBModel.thread_id)
                    .where(TriageDBModel.id.in_(triage_ids))
                    .where(TriageDBModel.thread_id.isnot(None))
                )
                thread_ids = [row[0] for row in result.fetchall()]
                logger.info(f"Found {len(thread_ids)} thread IDs to delete checkpoints for")
            except Exception as e:
                logger.error(f"Error getting thread IDs: {e}")
                stats["errors"] += 1

        # Step 2: Delete triages from database
        async with async_db_session() as session:
            try:
                delete_stmt = delete(TriageDBModel).where(
                    TriageDBModel.id.in_(triage_ids)
                )
                result = await session.execute(delete_stmt)
                stats["triages_deleted"] = result.rowcount
                await session.commit()
                logger.info(f"Deleted {stats['triages_deleted']} triage record(s)")
            except Exception as e:
                logger.error(f"Error deleting triages: {e}")
                logger.exception("Full error details:")
                await session.rollback()
                stats["errors"] += 1

        # Step 3: Delete checkpoints for those thread_ids
        if thread_ids:
            conn_string = os.environ.get("POSTGRES_CHECKPOINTER_CONN_STRING")
            if not conn_string:
                logger.warning("POSTGRES_CHECKPOINTER_CONN_STRING not set, skipping checkpoint cleanup")
            else:
                try:
                    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
                        await checkpointer.setup()

                        for thread_id in thread_ids:
                            try:
                                await checkpointer.adelete_thread(thread_id)
                                stats["checkpoints_deleted"] += 1
                                logger.debug(f"Deleted checkpoint for thread: {thread_id}")
                            except Exception as e:
                                logger.warning(f"Failed to delete checkpoint for thread {thread_id}: {e}")
                                stats["errors"] += 1

                            # Yield control periodically for garbage collection
                            if stats["checkpoints_deleted"] % 10 == 0:
                                await asyncio.sleep(0.1)

                    logger.info(f"Deleted {stats['checkpoints_deleted']} checkpoint(s)")
                except Exception as e:
                    logger.error(f"Error during checkpoint cleanup: {e}")
                    logger.exception("Full checkpoint cleanup error details:")
                    stats["errors"] += 1

        logger.info(f"Cleanup completed: {stats}")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        logger.exception("Full cleanup error details:")
        stats["errors"] += 1

    return stats


def execute_cleanup_job(triage_ids: list):
    """
    Execute cleanup job.

    Args:
        triage_ids: List of triage IDs to delete
    """
    job = get_current_job()
    job_id = job.id if job else "unknown"

    logger.info(f"Starting cleanup job {job_id} for {len(triage_ids)} triage(s)")
    start_time = time.time()

    try:
        stats = asyncio.run(cleanup_triages_and_checkpoints(triage_ids))
        processing_time = time.time() - start_time
        logger.info(f"Completed cleanup job {job_id} in {processing_time:.2f}s: {stats}")
        return stats
    except Exception:
        logger.exception(f"Failed to execute cleanup job {job_id}")
        processing_time = time.time() - start_time
        logger.error(f"Cleanup job {job_id} failed after {processing_time:.2f}s")
        raise


def enqueue_cleanup_job(triage_ids: list, depends_on_job_id: str = None) -> str:
    """
    Enqueue cleanup job in low_priority_triages queue.

    Args:
        triage_ids: List of triage IDs to delete
        depends_on_job_id: Optional job ID that must complete before cleanup runs

    Returns:
        Job ID of the enqueued cleanup job
    """
    if not triage_ids:
        logger.info("No triage IDs to clean up, skipping cleanup job")
        return ""

    queue = get_queue("low_priority_triages")

    # If depends_on_job_id is provided, cleanup will only run after that job completes
    job = queue.enqueue(
        execute_cleanup_job,
        triage_ids=triage_ids,
        job_timeout="10m",  # 10 minutes should be enough for cleanup
        depends_on=depends_on_job_id  # Cleanup runs AFTER triage completes
    )

    if depends_on_job_id:
        logger.info(f"Enqueued cleanup job {job.id} for {len(triage_ids)} triage(s) in low_priority_triages queue "
                    f"(depends on job {depends_on_job_id})")
    else:
        logger.info(f"Enqueued cleanup job {job.id} for {len(triage_ids)} triage(s) in low_priority_triages queue")

    return job.id

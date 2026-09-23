"""
Group Triage Job (Job 3)

Scheduler: Finds pending groups and enqueues triage jobs.
Worker: Performs RCA on one group using LangGraph.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.api.enums import Status
from src.server.models.db import (
    AlertGroupDBModel,
    AlertDBModel,
    TriageDBModel,
    EvaluationDBModel,
)
from src.alert_grouping.services import triage_alert_group
from src.server.utilities import get_queue

logger = logging.getLogger(__name__)


async def _update_alerts_triage_status(
    session: AsyncSession,
    group_id: int,
    thread_id: str | None,
    status: str,
    triage_result: dict | None,
):
    """
    Update triage status for all alerts in a group.

    Creates or updates Triage records with status and thread_id.
    When completed, also creates Evaluation records.

    Args:
        session: Database session
        group_id: ID of the alert group
        thread_id: LangGraph thread ID
        status: Triage status ('in_progress', 'completed', 'failed')
        triage_result: Unused (kept for compatibility)
    """
    status_map = {
        "in_progress": Status.PROCESSING,
        "completed": Status.SUCCESS,
        "failed": Status.ERROR,
    }

    triage_status = status_map.get(status, Status.PENDING)

    alerts = await session.scalars(
        select(AlertDBModel).where(AlertDBModel.group_id == group_id)
    )
    alert_list = list(alerts)

    for alert in alert_list:
        existing_triage = (
            await session.scalar(
                select(TriageDBModel).where(
                    TriageDBModel.alert_id == alert.id,
                    TriageDBModel.thread_id == thread_id,
                )
            )
            if thread_id
            else None
        )

        if existing_triage:
            existing_triage.status = triage_status
        else:
            new_triage = TriageDBModel(
                alert_id=alert.id,
                status=triage_status,
                thread_id=thread_id,
                job_id=None,
            )
            session.add(new_triage)

    await session.commit()
    logger.info(
        f"Updated triage status to '{status}' for all alerts in group {group_id}"
    )


# NOTE: Group-level evaluation is created in the main triage completion flow
# NOT here in _update_alerts_triage_status
# This function only updates individual alert triage status records


async def execute_group_triage_job_async(group_id: int, thread_id: str):
    """
    WORKER JOB: Process a single alert group triage.
    This is the actual job that gets enqueued and processed by RQ workers.

    OPTIMIZED: Uses two-transaction pattern to avoid holding database locks
    during long-running LangGraph execution (10-30+ minutes).

    Transaction 1: Verify group status (quick)
    LangGraph Execution: No database connection held
    Transaction 2: Update results (quick)

    Args:
        group_id: ID of the alert group to triage
        thread_id: LangGraph thread ID for checkpointing
    """
    logger.info(
        f"[GROUP TRIAGE JOB] Starting triage for group {group_id} with thread_id={thread_id}"
    )

    # TRANSACTION 1: Quick verification and status transition
    async with async_db_session() as session:
        stmt = select(AlertGroupDBModel).where(AlertGroupDBModel.id == group_id)
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise ValueError(f"Alert group {group_id} not found")

        # Verify the group is in a triageable state (queued or in_progress)
        if group.triage_status not in ("queued", "in_progress"):
            logger.warning(
                f"Group {group_id} triage_status is '{group.triage_status}', expected 'queued' or 'in_progress'. Skipping."
            )
            return

        # If status is "queued", update to "in_progress" now that worker is processing it
        if group.triage_status == "queued":
            group.triage_status = "in_progress"
            await session.commit()
            logger.info(f"Updated group {group_id} status from 'queued' to 'in_progress'")

        logger.info(
            f"Verified group {group_id} is ready for triage (status: {group.triage_status})"
        )

    # PERFORM TRIAGE WITHOUT HOLDING DATABASE CONNECTION
    # This is the long-running operation (10-30+ minutes)
    # No database locks are held during this time
    try:
        logger.info(
            f"Starting LangGraph execution for group {group_id} (no DB lock held)"
        )
        triage_result = await triage_alert_group(None, group_id, thread_id)
        logger.info(f"LangGraph execution completed for group {group_id}")

    except Exception as e:
        logger.exception(f"Failed to triage group {group_id}: {e}")

        # CRITICAL FIX: Retry logic with exponential backoff for failed groups
        # If we can't update the database, the group will be stuck in "in_progress" forever
        MAX_TRIAGE_RETRIES = 3  # Maximum number of triage retry attempts
        max_db_update_retries = 3

        for attempt in range(max_db_update_retries):
            try:
                async with async_db_session() as session:
                    stmt = select(AlertGroupDBModel).where(
                        AlertGroupDBModel.id == group_id
                    )
                    result = await session.execute(stmt)
                    group = result.scalar_one_or_none()

                    if group:
                        # Increment retry counter
                        group.retry_count = (group.retry_count or 0) + 1

                        # CRITICAL FIX: Implement retry mechanism
                        if group.retry_count < MAX_TRIAGE_RETRIES:
                            # Retry: Reset to pending for next attempt
                            group.triage_status = "pending"
                            group.error_message = f"Retry {group.retry_count}/{MAX_TRIAGE_RETRIES}: {str(e)[:800]}"
                            logger.warning(
                                f"Group {group_id} triage failed (attempt {group.retry_count}/{MAX_TRIAGE_RETRIES}). "
                                f"Will retry. Error: {str(e)[:200]}"
                            )
                        else:
                            # Give up: Mark as permanently failed
                            group.triage_status = "failed"
                            group.error_message = f"Failed after {group.retry_count} attempts: {str(e)[:800]}"
                            logger.error(
                                f"Group {group_id} triage permanently failed after {group.retry_count} attempts. "
                                f"Marking as failed."
                            )
                            # Update individual alerts to reflect failure
                            await _update_alerts_triage_status(
                                session, group_id, None, "failed", None
                            )

                        await session.commit()

                    logger.info(
                        f"Updated group {group_id} status (DB update attempt {attempt + 1}/{max_db_update_retries})"
                    )
                    break  # Success - exit retry loop

            except Exception as update_error:
                if attempt == max_db_update_retries - 1:
                    # Final attempt failed - this is critical
                    logger.critical(
                        f"CRITICAL: Failed to update group {group_id} status after {max_db_update_retries} attempts. "
                        f"Group may be stuck in 'in_progress' state. Manual intervention required.",
                        extra={
                            "error_id": "ERROR_GROUP_STATUS_UPDATE_CRITICAL",
                            "group_id": group_id,
                            "original_error": str(e),
                            "update_error": str(update_error),
                        },
                    )
                else:
                    # Retry with exponential backoff
                    backoff_seconds = 2**attempt
                    logger.warning(
                        f"Failed to update group {group_id} status (attempt {attempt + 1}/{max_db_update_retries}). "
                        f"Retrying in {backoff_seconds}s..."
                    )
                    await asyncio.sleep(backoff_seconds)

        raise

    # TRANSACTION 2 (SUCCESS PATH): Update results
    async with async_db_session() as session:
        try:
            # CRITICAL FIX: Eagerly load alerts relationship for fault mapping check
            from sqlalchemy.orm import selectinload

            stmt = (
                select(AlertGroupDBModel)
                .where(AlertGroupDBModel.id == group_id)
                .options(selectinload(AlertGroupDBModel.alerts))
            )
            result = await session.execute(stmt)
            group = result.scalar_one_or_none()

            if not group:
                raise ValueError(f"Alert group {group_id} not found after triage")

            # Update group with triage results and metrics
            group.root_cause_summary = triage_result.get("root_cause_summary", "")
            group.tokens_used = triage_result.get("tokens_used")
            group.price_usd = triage_result.get("price_usd")
            group.processing_time_sec = triage_result.get("processing_time_sec")
            group.llm_metrics = triage_result.get("llm_metrics")
            group.triage_status = "completed"
            group.triaged_at = datetime.now(timezone.utc)
            await session.commit()

            # Update individual alerts in the group to reflect group triage completion
            await _update_alerts_triage_status(
                session, group_id, thread_id, "completed", triage_result
            )

            logger.info(f"Triage completed for group {group.id}")
            logger.info(
                f"   RCA: {triage_result.get('root_cause_summary', '')[:100]}..."
            )
            logger.info(
                f"   Metrics: {triage_result.get('tokens_used')} tokens, "
                f"${triage_result.get('price_usd', 0):.4f}, "
                f"{triage_result.get('processing_time_sec')}s"
            )

            # CRITICAL FIX: Create group-level evaluation record and enqueue job if chaos disabled
            from src.server.utilities.config import is_chaos_system_enabled
            from src.triage_evaluation import enqueue_group_evaluation_job

            # Check if chaos system is enabled
            chaos_enabled = await is_chaos_system_enabled()

            # Check if group evaluation record already exists
            existing_group_eval = await session.scalar(
                select(EvaluationDBModel).where(EvaluationDBModel.group_id == group_id)
            )

            if existing_group_eval:
                # Update existing evaluation record
                group_eval_record = existing_group_eval
                logger.info(
                    f"group_id={group_id} -> Found existing group evaluation record (id={group_eval_record.id})"
                )
            else:
                # Create new group evaluation record
                group_eval_record = EvaluationDBModel(
                    group_id=group_id,
                    alert_id=None,  # Group evaluation, not alert-specific
                    status=Status.PENDING,
                )
                session.add(group_eval_record)
                await session.flush()  # Get the ID
                logger.info(
                    f"group_id={group_id} -> Created new group evaluation record (id={group_eval_record.id})"
                )

            if not chaos_enabled:
                # Only enqueue group evaluation job if chaos system is disabled
                # When chaos is enabled, fault ledger PUT will trigger evaluation
                logger.info(
                    f"group_id={group_id} -> Chaos system disabled, enqueueing group evaluation job"
                )
                group_eval_job_id = enqueue_group_evaluation_job(group_id=group_id)
                group_eval_record.job_id = group_eval_job_id
                group_eval_record.status = Status.QUEUED
            else:
                # RACE CONDITION FIX: Check if group is mapped to a fault ledger
                # If mapped, enqueue evaluation immediately (PUT already happened)
                from src.server.models.db import FaultLedgerToAlertMappingDBModel

                # Check if any alert in the group is mapped to a fault ledger
                is_mapped = False
                if group.alerts and len(group.alerts) > 0:
                    for alert in group.alerts:
                        mapping = await session.scalar(
                            select(FaultLedgerToAlertMappingDBModel).where(
                                FaultLedgerToAlertMappingDBModel.alert_id == alert.id
                            )
                        )
                        if mapping:
                            is_mapped = True
                            logger.info(
                                f"group_id={group_id} -> Alert {alert.id} is mapped to fault ledger {mapping.fault_ledger_id}"
                            )
                            break

                if is_mapped:
                    # PUT already happened - enqueue evaluation now
                    logger.info(
                        f"group_id={group_id} -> Chaos enabled but group is mapped to fault ledger, enqueueing evaluation job"
                    )
                    group_eval_job_id = enqueue_group_evaluation_job(group_id=group_id)
                    group_eval_record.job_id = group_eval_job_id
                    group_eval_record.status = Status.QUEUED
                else:
                    # PUT hasn't happened yet - wait for it
                    logger.info(
                        f"group_id={group_id} -> Chaos enabled and no fault mapping found, waiting for PUT request"
                    )

            await session.commit()
            logger.info(f"Group evaluation record created/updated for group {group_id}")

        except Exception as e:
            logger.exception(
                f"Failed to update group {group_id} with triage results: {e}"
            )
            raise


def execute_group_triage_job(group_id: int, thread_id: str):
    """
    WORKER JOB: Synchronous wrapper for the async group triage job.
    This is what gets called by RQ workers.
    """
    asyncio.run(execute_group_triage_job_async(group_id, thread_id))


async def enqueue_pending_groups_async():
    """
    SCHEDULER JOB: Find pending groups and enqueue them as separate RQ jobs.
    This runs every 5 minutes and enqueues groups, but doesn't process them.
    """
    logger.info("[JOB 3: GROUP TRIAGE SCHEDULER] Finding pending groups")

    try:
        # Check if automatic triage is enabled (master switch)
        from src.server.utilities.config import is_automatic_triage_enabled

        if not await is_automatic_triage_enabled():
            logger.info("[JOB 3: GROUP TRIAGE SCHEDULER] Automatic triage is disabled - skipping")
            return

        async with async_db_session() as session:
            # CRITICAL FIX: Check if any triage (group OR standalone) is already in progress
            # This prevents parallel triaging which causes rate limit errors

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
                logger.info(f"Skipping group triage enqueue:")
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

            # Fetch all groups that need triage (no limit - enqueue all pending groups)
            stmt = (
                select(AlertGroupDBModel)
                .where(
                    AlertGroupDBModel.status == "active",
                    AlertGroupDBModel.triage_status == "pending",
                )
                .order_by(AlertGroupDBModel.created_at.asc())
            )

            result = await session.execute(stmt)
            pending_groups = result.scalars().all()

            if not pending_groups:
                logger.info("No pending groups found for triage")
                return

            logger.info(f"Found {len(pending_groups)} groups pending triage")

            # Get the queue from environment variable
            queue_name = os.getenv("RQ_TRIAGE_QUEUE_NAME", "group_triage")
            queue = get_queue(queue_name)
            logger.info(f"Using queue: {queue_name}")

            # CRITICAL FIX: Only enqueue ONE group at a time to avoid rate limit errors
            # The scheduler runs every 5 minutes, so the next group will be picked up
            # after the current one completes
            group = pending_groups[0]  # Take the oldest pending group

            try:
                # Generate thread_id for LangGraph checkpointing
                thread_id = str(uuid.uuid4())

                # Mark as in_progress and store thread_id
                group.triage_status = "in_progress"
                group.thread_id = thread_id
                await session.commit()

                # Update individual alerts in the group to reflect that triage has started
                await _update_alerts_triage_status(
                    session, group.id, thread_id, "in_progress", None
                )

                # Enqueue the job with a generous but finite timeout.
                # Group triage can take a long time (10-30+ minutes) due to
                # LangGraph orchestration and LLM calls, so we allow up to 60
                # minutes before RQ considers the job failed.
                job = queue.enqueue(
                    execute_group_triage_job,
                    group_id=group.id,
                    thread_id=thread_id,
                    job_timeout="60m",  # 60 minutes timeout for group triage
                )

                logger.info(
                    f"Enqueued group {group.id} as job {job.id} with thread_id={thread_id}"
                )
                logger.info(f"   Remaining pending groups: {len(pending_groups) - 1}")

            except Exception as e:
                logger.exception(f"Failed to enqueue group {group.id}: {e}")

    except Exception:
        logger.exception("Error in group triage scheduler")
        raise

    finally:
        logger.info("[JOB 3: GROUP TRIAGE SCHEDULER] Completed")


def run_group_triage_scheduler():
    """
    SCHEDULER: Synchronous wrapper for the async scheduler job.
    This is called by RQ scheduler every 5 minutes to enqueue pending groups.
    """
    logger.info("[JOB 3: GROUP TRIAGE SCHEDULER] Triggered by scheduler")

    try:
        # Run the async scheduler
        asyncio.run(enqueue_pending_groups_async())
        logger.info("[JOB 3: GROUP TRIAGE SCHEDULER] Completed successfully")

    except Exception:
        logger.exception("[JOB 3: GROUP TRIAGE SCHEDULER] Failed with exception")
        raise


if __name__ == "__main__":
    # For manual testing
    run_group_triage_scheduler()

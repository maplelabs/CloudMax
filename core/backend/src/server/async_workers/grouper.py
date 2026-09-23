#!/usr/bin/env python3
"""
RQ Worker script for processing alert grouping and correlation background jobs.

This is the SINGLE WORKER that handles ALL alert grouping and correlation jobs:
- Worker 1: Batch alert grouping (scheduled job)
- Worker 2: Ungrouped alert retry (scheduled job)
- Worker 3: Group triage scheduling (scheduled job)
- Individual group triage jobs (enqueued by Worker 3)

IMPORTANT: This worker should run as a SINGLE INSTANCE only.
- Group triage uses LangGraph with async PostgreSQL checkpointer
- Running multiple workers in parallel can cause:
  * Database connection pool exhaustion
  * Async context conflicts
  * Checkpoint database locking issues
- Jobs are processed SEQUENTIALLY (one at a time) by design

Usage:
    python -m src.server.async_workers.grouper
"""
import logging
import os

from src.server.utilities import get_redis_connection, get_queue
from .common import (
    generate_unique_worker_name,
    cleanup_stale_workers,
    setup_logging,
    setup_environment,
    create_and_start_worker,
)

logger = logging.getLogger(__name__)


def main():
    """Main grouper worker function."""

    # Setup environment and logging
    setup_environment()
    setup_logging()

    # Get queue names from environment variables
    grouping_queue = os.getenv("RQ_GROUPING_QUEUE_NAME", "alert_grouping")
    triage_queue = os.getenv("RQ_TRIAGE_QUEUE_NAME", "group_triage")

    # This worker listens to both queues
    queue_names = [grouping_queue, triage_queue]

    logger.info(f"Starting RQ grouper worker for queues: {queue_names}")
    logger.info(f"  - Grouping queue: {grouping_queue}")
    logger.info(f"  - Triage queue: {triage_queue}")

    try:
        # Get Redis connection
        redis_conn = get_redis_connection()

        # Generate unique worker name
        worker_name = generate_unique_worker_name("grouper")

        # Clean up any stale workers
        cleanup_stale_workers(redis_conn, worker_name)

        # Create queues
        queues = [get_queue(name) for name in queue_names]

        # Create and start worker
        create_and_start_worker(queues, redis_conn, worker_name)

        logger.info("Grouper worker started successfully")

    except Exception:

        logger.exception("Grouper worker startup failed")
        raise


if __name__ == "__main__":
    main()

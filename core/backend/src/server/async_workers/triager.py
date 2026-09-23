#!/usr/bin/env python3
"""
RQ Worker script for processing triage background jobs.

Usage:
    python -m src.platform.async_workers.triager
"""
import logging

from src.server.utilities import get_redis_connection, get_queue
from .common import (generate_unique_worker_name, cleanup_stale_workers, setup_logging, setup_environment,
                     create_and_start_worker)

logger = logging.getLogger(__name__)


def main():
    """Main triage worker function."""

    # Setup environment and logging
    setup_environment()
    setup_logging()

    # Get queue names from environment variable
    queue_names = [
        "high_priority_triages",
        "medium_priority_triages",
        "low_priority_triages"
    ]

    logger.info(f"Starting RQ triage worker for queues: {queue_names}")

    try:
        # Get Redis connection
        redis_conn = get_redis_connection()

        # Generate unique worker name
        worker_name = generate_unique_worker_name("triager")

        # Clean up any stale workers
        cleanup_stale_workers(redis_conn, worker_name)

        # Create queues
        queues = [
            get_queue(name) for name in queue_names
        ]

        # TODO: Create a worker manager here instead which helps to create and manage multiple workers
        #  i.e., It uses #orchestrators config to determine number of workers
        #  https://python-rq.org/docs/workers/#shutting-down-a-worker

        # Create and start worker
        create_and_start_worker(queues, redis_conn, worker_name)

        logger.info("Triage worker started successfully")

    except Exception:
        logger.exception("Triage worker startup failed")
        raise


if __name__ == "__main__":
    main()

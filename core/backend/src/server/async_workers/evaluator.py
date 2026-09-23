#!/usr/bin/env python3
"""
RQ Worker script for processing evaluation background jobs.

Usage:
    python -m src.platform.async_workers.evaluator
"""
import logging

from src.server.utilities import get_redis_connection, get_queue
from .common import (generate_unique_worker_name, cleanup_stale_workers, setup_logging, setup_environment,
                     create_and_start_worker)

logger = logging.getLogger(__name__)


def main():
    """Main evaluation worker function."""

    # Setup environment and logging
    setup_environment()
    setup_logging()

    # Get queue names from environment variable, default to evaluation queues
    queue_names = [
        "triages_to_evaluate",
        "group_evaluations",  # Added to process group evaluation jobs
        "default"  # For general background jobs (e.g., Confluence sync)
    ]

    logger.info(f"Starting RQ evaluation worker for queues: {queue_names}")

    try:
        # Get Redis connection
        redis_conn = get_redis_connection()

        # Generate unique worker name
        worker_name = generate_unique_worker_name("evaluator")

        # Clean up any stale workers
        cleanup_stale_workers(redis_conn, worker_name)

        # Create queues
        queues = [
            get_queue(name) for name in queue_names
        ]

        # TODO: Not sure if we need a worker pool manager here. May be necessary for multiple evals

        # Create and start worker
        create_and_start_worker(queues, redis_conn, worker_name)

        logger.info("Evaluation worker started successfully")

    except Exception:

        logger.exception("Evaluation worker startup failed")
        raise


if __name__ == "__main__":
    main()

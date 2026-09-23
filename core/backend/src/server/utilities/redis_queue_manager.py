"""
Redis connection management for the queue system.
"""

import logging
import os
from typing import Optional

import redis
from rq import Queue
from rq_scheduler import Scheduler

logger = logging.getLogger(__name__)

# Global Redis connection instance
_redis_connection: Optional[redis.Redis] = None


def get_redis_connection() -> redis.Redis:
    """
    Get or create Redis connection for the queue system.
    
    Returns:
        redis.Redis: Redis connection instance
    """
    global _redis_connection

    if _redis_connection is None:
        # Get configuration from environment
        redis_host = os.getenv("REDIS_QUEUE_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_QUEUE_PORT", "6379"))
        redis_password = os.getenv("REDIS_QUEUE_AUTH", "queueredissecret")
        redis_db = int(os.getenv("REDIS_QUEUE_DB", "1"))

        logger.info(f"Connecting to Redis queue at {redis_host}:{redis_port}")

        _redis_connection = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            db=redis_db,
            decode_responses=False,  # Let RQ handle encoding
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )

        # Test the connection
        try:
            _redis_connection.ping()
            logger.info("Successfully connected to Redis queue")
        except redis.ConnectionError as e:
            logger.exception(f"Failed to connect to Redis queue")
            _redis_connection = None
            raise

    return _redis_connection


def get_queue(name: str = "default") -> Queue:
    """
    Get RQ Queue instance.

    Args:
        name: Queue name (default, high, low)

    Returns:
        Queue: RQ Queue instance with extended default timeout (30 minutes)
    """
    redis_conn = get_redis_connection()
    # Set default_timeout to 30 minutes (1800 seconds) to allow long-running jobs
    # Individual jobs can override this with timeout parameter in enqueue()
    return Queue(name, connection=redis_conn, default_timeout=1800)


def clear_redis_queues():
    """Clear all RQ queues and job data from Redis."""
    try:
        redis_conn = get_redis_connection()

        # Get all RQ-related keys
        rq_keys = list(redis_conn.scan_iter(match="rq:*"))

        if rq_keys:
            logger.info(f"Clearing {len(rq_keys)} RQ keys from Redis")
            redis_conn.delete(*rq_keys)
            logger.info("Successfully cleared all RQ data from Redis")
        else:
            logger.info("No RQ keys found in Redis")

    except Exception:

        logger.exception(f"Failed to clear Redis queues")
        raise


def close_redis_connection():
    """Close the Redis connection."""
    global _redis_connection
    if _redis_connection:
        _redis_connection.close()
        _redis_connection = None
        logger.info("Redis queue connection closed")


def get_scheduler(queue_name: str) -> Scheduler:
    """Returns the RQ scheduler instance for a specific queue."""
    queue = get_queue(queue_name)
    scheduler = Scheduler(connection=queue.connection, queue=queue)
    return scheduler

"""
Common utilities for async workers.
Shared functionality between triage and evaluation workers.
"""
import logging
import os
import socket
import sys
import time
import uuid

from dotenv import load_dotenv
from rq import Worker

logger = logging.getLogger(__name__)


def generate_unique_worker_name(prefix: str) -> str:
    """
    Generate a unique worker name to avoid conflicts.

    Returns:
        str: Unique worker name
    """
    # TODO: Probably need to use different strategy else we'll create new workers for every upgrade.
    hostname = socket.gethostname()
    container_id = os.environ.get('HOSTNAME', hostname)[:12]
    unique_id = str(uuid.uuid4())[:8]

    return f"{prefix}-{container_id}-{unique_id}"


def cleanup_stale_workers(redis_conn, worker_name: str):
    """
    Clean up any stale worker registrations in Redis.

    Args:
        redis_conn: Redis connection
        worker_name: Name of the current worker
    """
    try:
        # Get all registered workers
        workers = Worker.all(connection=redis_conn)

        stale_workers = []
        for worker in workers:
            try:
                # Check if worker is actually running by trying to get its state
                # If the worker process is dead, this will help identify stale workers
                worker_key = f"rq:worker:{worker.name}"
                worker_data = redis_conn.hgetall(worker_key)

                if not worker_data or worker.name == worker_name:
                    continue

                # Check if worker heartbeat is stale (older than 5 minutes)
                last_heartbeat = worker_data.get(b'last_heartbeat', b'0')
                if last_heartbeat:
                    heartbeat_time = float(last_heartbeat.decode())
                    if time.time() - heartbeat_time > 300:  # 5 minutes
                        stale_workers.append(worker)

            except Exception as e:
                logger.debug(f"Error checking worker {worker.name}: {e}")
                continue

        # Clean up stale workers
        for worker in stale_workers:
            try:
                logger.info(f"Cleaning up stale worker: {worker.name}")
                # Remove worker from Redis
                worker_key = f"rq:worker:{worker.name}"
                redis_conn.delete(worker_key)
                # Remove from workers set
                redis_conn.srem('rq:workers', worker.name)
            except Exception as e:
                logger.warning(f"Failed to cleanup worker {worker.name}: {e}")

    except Exception as e:
        logger.warning(f"Failed to cleanup stale workers: {e}")


def setup_logging():
    """Configure logging for workers."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s'
    )


def setup_environment():
    """Setup environment and Python path."""
    # Add the backend directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    # Load environment variables
    load_dotenv()


def create_and_start_worker(queues, redis_conn, worker_name: str):
    """
    Create and start an RQ worker.

    Args:
        queues: List of queue objects
        redis_conn: Redis connection
        worker_name: Unique worker name
    """
    # Create worker with extended default job timeout (30 minutes = 1800 seconds)
    # This allows jobs to specify their own timeout via timeout parameter
    # The default_result_ttl keeps job results for 500 seconds
    worker = Worker(
        queues,
        connection=redis_conn,
        name=worker_name,
        default_result_ttl=500,  # Keep results for 500 seconds
        job_monitoring_interval=30,  # Check job status every 30 seconds
        default_worker_ttl=1800,  # Worker TTL in seconds (30 minutes)
    )

    # Start processing jobs
    # Jobs can override timeout via timeout parameter in enqueue()
    worker.work(logging_level='INFO')

"""
Docker Container Restart Chaos Actions

This module provides chaos engineering actions for restarting Docker containers.
"""

import logging
import time
import random
from typing import List, Optional
import docker
from docker.errors import NotFound, APIError

__all__ = ["restart_docker_containers", "restart_docker_containers_continuous"]

logger = logging.getLogger("chaostoolkit")


def restart_docker_containers(
    container_names: Optional[List[str]] = None,
    label_filter: Optional[dict] = None,
    qty: int = 1,
    rand: bool = False,
    timeout: int = 10,
) -> List[dict]:
    """
    Restart Docker containers by name or label filter.

    Args:
        container_names: List of container names to restart
        label_filter: Dictionary of labels to filter containers (e.g., {"app": "nginx"})
        qty: Number of containers to restart
        rand: If True, randomly select containers to restart
        timeout: Timeout in seconds for container restart

    Returns:
        List of dictionaries with container restart information

    Example:
        # Restart specific containers
        restart_docker_containers(container_names=["nginx", "redis"])

        # Restart containers by label
        restart_docker_containers(label_filter={"app": "web"}, qty=2, rand=True)
    """
    logger.info("🐳 Starting Docker container restart chaos action")

    try:
        client = docker.from_env()
    except Exception as e:
        logger.error(f"❌ Failed to connect to Docker: {e}")
        raise

    # Get containers to restart
    containers = []

    if container_names:
        logger.info(f"📋 Looking for containers by name: {container_names}")
        for name in container_names:
            try:
                container = client.containers.get(name)
                containers.append(container)
                logger.info(f"   ✅ Found container: {name}")
            except NotFound:
                logger.warning(f"   ⚠️  Container not found: {name}")

    elif label_filter:
        logger.info(f"🏷️  Looking for containers with labels: {label_filter}")
        filters = {"label": [f"{k}={v}" for k, v in label_filter.items()]}
        containers = client.containers.list(filters=filters)
        logger.info(f"   ✅ Found {len(containers)} containers")

    else:
        logger.error("❌ Either container_names or label_filter must be provided")
        raise ValueError("Either container_names or label_filter must be provided")

    if not containers:
        logger.warning("⚠️  No containers found to restart")
        return []

    # Select containers to restart
    if rand and len(containers) > qty:
        containers = random.sample(containers, qty)
        logger.info(f"🎲 Randomly selected {qty} containers")
    else:
        containers = containers[:qty]
        logger.info(f"📌 Selected first {len(containers)} containers")

    # Restart containers
    results = []
    for container in containers:
        try:
            container_name = container.name
            container_id = container.id[:12]

            logger.info(f"🔄 Restarting container: {container_name} ({container_id})")

            start_time = time.time()
            container.restart(timeout=timeout)
            elapsed = time.time() - start_time

            logger.info(f"   ✅ Container restarted successfully in {elapsed:.2f}s")

            results.append({
                "name": container_name,
                "id": container_id,
                "status": "restarted",
                "elapsed_time": elapsed
            })

        except APIError as e:
            logger.error(f"   ❌ Failed to restart container {container.name}: {e}")
            results.append({
                "name": container.name,
                "id": container.id[:12],
                "status": "failed",
                "error": str(e)
            })

    logger.info(f"✅ Restart operation completed. {len(results)} containers processed")
    return results


def restart_docker_containers_continuous(
    container_names: Optional[List[str]] = None,
    label_filter: Optional[dict] = None,
    qty: int = 1,
    rand: bool = False,
    timeout: int = 10,
    interval: int = 30,
    duration: int = 300,
) -> dict:
    """
    Continuously restart Docker containers at specified intervals.

    Args:
        container_names: List of container names to restart
        label_filter: Dictionary of labels to filter containers
        qty: Number of containers to restart per cycle
        rand: If True, randomly select containers to restart
        timeout: Timeout in seconds for container restart
        interval: Time in seconds between restart cycles
        duration: Total duration in seconds to run the experiment

    Returns:
        Dictionary with summary of restart operations
    """
    logger.info("🚀 Starting continuous Docker container restart experiment")
    logger.info(f"   Duration: {duration}s, Interval: {interval}s")

    start_time = time.time()
    restart_count = 0
    total_containers_restarted = 0

    while time.time() - start_time < duration:
        restart_count += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 Restart Cycle #{restart_count}")
        logger.info(f"{'='*60}")

        try:
            results = restart_docker_containers(
                container_names=container_names,
                label_filter=label_filter,
                qty=qty,
                rand=rand,
                timeout=timeout
            )

            successful = len([r for r in results if r["status"] == "restarted"])
            total_containers_restarted += successful

            logger.info(f"   ✅ Cycle #{restart_count}: {successful}/{len(results)} containers restarted")

        except Exception as e:
            logger.error(f"   ❌ Error in cycle #{restart_count}: {e}")

        # Sleep until next cycle (unless we're done)
        elapsed = time.time() - start_time
        if elapsed < duration:
            sleep_time = min(interval, duration - elapsed)
            logger.info(f"   ⏳ Sleeping for {sleep_time:.0f}s until next cycle...")
            time.sleep(sleep_time)

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Continuous restart experiment completed")
    logger.info(f"   Total cycles: {restart_count}")
    logger.info(f"   Total containers restarted: {total_containers_restarted}")
    logger.info(f"{'='*60}")

    return {
        "total_cycles": restart_count,
        "total_containers_restarted": total_containers_restarted,
        "duration": time.time() - start_time
    }
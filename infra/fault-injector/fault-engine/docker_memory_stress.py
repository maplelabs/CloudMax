"""
Docker Container Memory Stress Chaos Actions

This module provides chaos engineering actions for gradually increasing memory
pressure in Docker containers and simulating OOM conditions.
"""

import docker
import time
import logging
from typing import Dict, Any
from docker.errors import NotFound, APIError

__all__ = ["gradual_memory_stress_and_kill"]

logger = logging.getLogger("chaostoolkit")


def gradual_memory_stress_and_kill(
    container_name: str,
    num_workers: int = 10,
    memory_per_worker_mb: int = 50,
    stagger_interval: int = 15,
    worker_duration: int = 90,
    kill_at_iteration: int = 8,
    kill_signal: str = "SIGKILL",
    total_duration: int = 300,
    sleep_after_kill: int = 5,
    sleep_after_restart: int = 15,
    scenario_name: str = "Memory Stress Test",
    scenario_description: str = "Gradual memory stress experiment"
) -> Dict[str, Any]:
    """
    Repeatedly kill container multiple times over total_duration.
    Each cycle: gradually increase memory → kill at threshold → restart → repeat.
    Uses all available time - partial cycles continue until duration expires.
    Workers auto-expire after worker_duration (no manual cleanup needed).
    Uses stress-ng with --vm-hang for minimal CPU usage (~2-5%) while stressing memory.

    Args:
        container_name: Name of the Docker container to stress
        num_workers: Total number of stress workers to spawn per cycle
        memory_per_worker_mb: Memory each worker allocates (in MB)
        stagger_interval: Seconds between spawning each worker
        worker_duration: How long each worker runs (seconds) - workers auto-expire
        kill_at_iteration: Which iteration to kill the container
        kill_signal: Signal to send to container (SIGKILL/SIGTERM/etc)
        total_duration: Total experiment duration in seconds
        sleep_after_kill: Seconds to sleep after kill, before restart
        sleep_after_restart: Seconds to sleep after restart, before next cycle
        scenario_name: Name of the test scenario
        scenario_description: Description of the test scenario

    Returns:
        Dictionary containing total_cycles, complete_cycles, partial_cycles,
        total_kills, total_duration, and cycles data
    """

    # Calculate values
    total_memory_mb = num_workers * memory_per_worker_mb
    kill_at_memory_mb = kill_at_iteration * memory_per_worker_mb
    experiment_start_time = time.time()

    logger.info("=" * 60)
    logger.info(" Gradual Memory Stress + Multiple Kills")
    logger.info("=" * 60)
    logger.info(f"Scenario:             {scenario_name}")
    logger.info(f"Description:          {scenario_description}")
    logger.info(f"Container:            {container_name}")
    logger.info(f"Workers per cycle:    {num_workers}")
    logger.info(f"Memory per worker:    {memory_per_worker_mb}MB")
    logger.info(f"Stagger interval:     {stagger_interval}s")
    logger.info(f"Worker duration:      {worker_duration}s")
    logger.info(f"Kill at iteration:    {kill_at_iteration} ({kill_at_memory_mb}MB)")
    logger.info(f"Kill signal:          {kill_signal}")
    logger.info(f"Total duration:       {total_duration}s")
    logger.info(f"Sleep after kill:     {sleep_after_kill}s")
    logger.info(f"Sleep after restart:  {sleep_after_restart}s")
    logger.info(f"Total target memory:  {total_memory_mb}MB")
    logger.info(f"Started at:           {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    logger.info("")
    logger.info("ℹ️  This script runs on HOST and executes stress-ng inside container")
    logger.info("")

    # Connect to Docker
    try:
        client = docker.from_env()
    except Exception as e:
        logger.error(f"❌ Failed to connect to Docker: {e}")
        raise

    # Validate container exists and is running
    try:
        container = client.containers.get(container_name)
        if container.status != 'running':
            raise ValueError(f"❌ ERROR: Container '{container_name}' is not running (status: {container.status})")
        logger.info(f"✅ Container '{container_name}' is running")
    except NotFound:
        logger.error(f"❌ ERROR: Container '{container_name}' not found")
        logger.info("")
        logger.info("Available containers:")
        for c in client.containers.list():
            logger.info(f"  {c.name}\t{c.status}")
        raise

    # Check if stress-ng is available in container
    try:
        exit_code, _ = container.exec_run("which stress-ng")
        if exit_code != 0:
            logger.error("❌ ERROR: stress-ng not found in container")
            logger.info("")
            logger.info("Install stress-ng in the container first:")
            logger.info(f"  docker exec -u root {container_name} sh -c 'apt-get update && apt-get install -y stress-ng'")
            raise RuntimeError("stress-ng not installed in container")
    except Exception as e:
        logger.error(f"❌ Failed to check for stress-ng: {e}")
        raise

    # Track all cycles
    all_cycles = []
    cycle_number = 0

    # Main loop - repeat until total_duration is reached
    while (time.time() - experiment_start_time) < total_duration:
        cycle_number += 1

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"🔄 CYCLE #{cycle_number}")
        logger.info("=" * 60)
        logger.info("")

        # Main stress loop for this cycle
        iterations_completed = 0
        container_killed = False

        for i in range(1, num_workers + 1):
            # Check if total duration exceeded
            if (time.time() - experiment_start_time) >= total_duration:
                logger.info("")
                logger.info("⏱️  Total duration reached")
                logger.info(f"✅ Completed {iterations_completed} iterations in this cycle")
                logger.info(f"✅ Workers will auto-expire after {worker_duration}s")
                break

            current_total = i * memory_per_worker_mb

            logger.info(f"[{time.strftime('%H:%M:%S')}] Iteration {i}/{num_workers}")
            logger.info(f"  → Adding {memory_per_worker_mb}MB inside container")
            logger.info(f"  → Approx total memory pressure: {current_total}MB")

            # Execute stress-ng inside container (detached)
            # Using --vm-hang 0 for minimal CPU usage while holding memory
            try:
                container.exec_run(
                    cmd=f"stress-ng --vm 1 --vm-bytes {memory_per_worker_mb}M --vm-hang 0 --timeout {worker_duration}s --quiet",
                    detach=True
                )
                logger.info(f"  → stress-ng started inside container")
            except Exception as e:
                logger.error(f"  ❌ Failed to start stress-ng: {e}")
                raise

            iterations_completed = i

            # Check if we should kill the container
            if i == kill_at_iteration:
                logger.info("")
                logger.info(f"🔥 KILL ITERATION REACHED ({kill_at_iteration})")
                logger.info(f"💀 Sending {kill_signal} to container '{container_name}'")
                logger.info("")

                try:
                    container.kill(signal=kill_signal)
                    container_killed = True
                    logger.info("✅ Kill signal sent")
                    logger.info("🛑 Exiting stress loop")
                except Exception as e:
                    logger.error(f"❌ Failed to kill container: {e}")
                    raise

                break

            logger.info("")
            time.sleep(stagger_interval)



        # Only proceed with kill/restart if we actually killed the container
        if not container_killed:
            logger.info("")
            logger.info(f"⚠️  Partial cycle - reached {iterations_completed}/{kill_at_iteration} iterations")
            logger.info(f"✅ Memory pressure: {iterations_completed * memory_per_worker_mb}MB")
            logger.info("✅ Workers will auto-expire - no restart needed")

            # Record partial cycle
            all_cycles.append({
                "cycle": cycle_number,
                "type": "partial",
                "iterations_completed": iterations_completed,
                "memory_reached": iterations_completed * memory_per_worker_mb,
                "container_killed": False
            })
            break

        # Wait for container to terminate
        logger.info("")
        logger.info("=" * 60)
        logger.info("Waiting for container to terminate...")
        logger.info("=" * 60)

        time.sleep(3)

        # Get exit code
        try:
            container.reload()
            exit_code = container.attrs['State']['ExitCode']
        except Exception as e:
            logger.error(f"❌ Failed to get exit code: {e}")
            exit_code = "unknown"

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"Cycle #{cycle_number} Result")
        logger.info("=" * 60)
        logger.info(f"Container Exit Code: {exit_code}")

        if exit_code == 137:
            logger.info("✅ Exit code 137 → SIGKILL (OOM-like behavior)")
            logger.info("✅ FAULT INJECTION SUCCESSFUL")
            status = "success"
        elif exit_code == 0:
            logger.info("⚠️  Exit code 0 → Normal exit (not killed)")
            status = "unexpected_normal_exit"
        else:
            logger.info(f"⚠️  Unexpected exit code: {exit_code}")
            status = "unexpected_exit_code"

        logger.info(f"Cycle ended at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # Sleep after kill (5 seconds)
        logger.info("")
        logger.info(f"⏳ Sleeping {sleep_after_kill} seconds after kill...")
        time.sleep(sleep_after_kill)

        # Auto-restart container
        logger.info("")
        logger.info("=" * 60)
        logger.info("Container Recovery")
        logger.info("=" * 60)
        logger.info(f"🔄 Restarting container: {container_name}")

        restart_start = time.time()

        try:
            container.start()
            logger.info("✅ Container restart initiated")
        except Exception as e:
            logger.error(f"❌ Failed to restart container: {e}")
            all_cycles.append({
                "cycle": cycle_number,
                "exit_code": exit_code,
                "recovery_time": None,
                "status": "restart_failed",
                "iterations_completed": iterations_completed,
                "memory_at_kill": kill_at_memory_mb,
                "container_healthy": False,
                "error": str(e)
            })
            break

        # Wait for container to be healthy
        logger.info("⏳ Waiting for container to become healthy...")

        retry_count = 0
        max_retries = 30
        container_healthy = False

        while retry_count < max_retries:
            try:
                container.reload()
                container_status = container.status

                # Check health status if available
                health_status = None
                if 'Health' in container.attrs['State']:
                    health_status = container.attrs['State']['Health']['Status']

                if container_status == 'running':
                    if health_status == 'healthy' or health_status is None:
                        restart_end = time.time()
                        recovery_time = restart_end - restart_start
                        logger.info("✅ Container is healthy and running")
                        logger.info(f"⏱️  Recovery time: {recovery_time:.0f} seconds")
                        container_healthy = True
                        break
            except Exception as e:
                logger.warning(f"⚠️  Error checking container status: {e}")

            time.sleep(1)
            retry_count += 1

        if not container_healthy:
            logger.warning("⚠️  Container started but health check timeout")
            recovery_time = time.time() - restart_start
        else:
            recovery_time = time.time() - restart_start

        # Show final status
        logger.info("")
        logger.info("📊 Container Status After Recovery:")
        try:
            container.reload()
            logger.info(f"   {container.name}\t{container.status}")
            if 'Health' in container.attrs['State']:
                logger.info(f"   Health: {container.attrs['State']['Health']['Status']}")
        except Exception as e:
            logger.error(f"   ❌ Container not running")

        logger.info("=" * 60)

        # Record this complete cycle
        all_cycles.append({
            "cycle": cycle_number,
            "type": "complete",
            "exit_code": exit_code,
            "recovery_time": recovery_time,
            "status": status,
            "iterations_completed": iterations_completed,
            "memory_at_kill": kill_at_memory_mb,
            "container_healthy": container_healthy,
            "container_killed": True
        })

        # Sleep after restart before next cycle (15 seconds)
        logger.info("")
        logger.info(f"⏳ Sleeping {sleep_after_restart} seconds before next cycle...")
        time.sleep(sleep_after_restart)

    # Final summary
    total_experiment_time = time.time() - experiment_start_time
    complete_cycles = [c for c in all_cycles if c.get('type') == 'complete']
    partial_cycles = [c for c in all_cycles if c.get('type') == 'partial']

    logger.info("")
    logger.info("=" * 60)
    logger.info("Experiment Summary")
    logger.info("=" * 60)
    logger.info(f"Total cycles:         {len(all_cycles)}")
    logger.info(f"Complete cycles:      {len(complete_cycles)} (killed at {kill_at_memory_mb}MB)")
    logger.info(f"Partial cycles:       {len(partial_cycles)} (time expired)")
    logger.info(f"Total duration:       {total_experiment_time:.0f}s / {total_duration}s")

    if complete_cycles:
        avg_recovery = sum(c['recovery_time'] for c in complete_cycles) / len(complete_cycles)
        logger.info(f"Avg recovery time:    {avg_recovery:.0f}s")

    if partial_cycles:
        for pc in partial_cycles:
            logger.info(f"Partial cycle #{pc['cycle']}: {pc['memory_reached']}MB ({pc['iterations_completed']} workers)")

    logger.info(f"Workers auto-expire:  ✅ Yes (after {worker_duration}s)")
    logger.info(f"Ended at:             {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Return results
    return {
        "total_cycles": len(all_cycles),
        "complete_cycles": len(complete_cycles),
        "partial_cycles": len(partial_cycles),
        "total_kills": len(complete_cycles),
        "total_duration": total_experiment_time,
        "cycles": all_cycles
    }


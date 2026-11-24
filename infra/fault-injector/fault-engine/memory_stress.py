import datetime
import time
import logging
from typing import Any, Dict, Optional
from chaoslib.types import Secrets
from chaosk8s.chaosmesh.stress.actions import stress_memory, delete_stressor

__all__ = ["stress_memory_gradual_cycles", "perform_single_gradual_cycle"]
logger = logging.getLogger("chaostoolkit")

def stress_memory_gradual_cycles(
    name: str = "memory-stress",
    workers: Optional[int] = 1,
    start_size: Optional[str] = "50MB",
    max_size: Optional[str] = "400MB",
    increment_mb: int = 50,
    oom_score: Optional[int] = 1000,
    label_selectors: Optional[str] = None,
    mode: str = "all",
    ns: str = "default",
    interval: int = 10,
    ramp_duration: int = 60,        # Time to reach OOM (1 minute)
    total_duration: int = 300,      # Total experiment time (5 minutes)
    recovery_wait: int = 30,        # Wait for pod restart after OOM
    secrets: Secrets = None,
) -> Dict[str, Any]:
    """
    Repeatedly perform gradual memory stress cycles until total_duration.
    
    Each cycle:
    1. Gradually increase memory over ramp_duration (1 min)
    2. Trigger OOM kill
    3. Wait for pod recovery
    4. Repeat until total_duration
    """
    print(f"🚀 Starting REPEATED gradual memory stress cycles")
    print(f"🔄 Cycle duration: {ramp_duration}s (gradual ramp to OOM)")
    print(f"⏱️  Total experiment: {total_duration}s")
    print(f"📈 Memory ramp: {start_size} → {max_size} (+{increment_mb}MB/{interval}s)")
    print(f"🎯 Target: {label_selectors}")
    print(f"⏳ Recovery wait: {recovery_wait}s between cycles")

    experiment_start = time.time()
    cycle_count = 0
    total_oom_events = 0

    while time.time() - experiment_start < total_duration:
        cycle_count += 1
        remaining_time = total_duration - (time.time() - experiment_start)

        print(f"\n{'🔥'*20} CYCLE #{cycle_count} {'🔥'*20}")
        print(f"⏰ Remaining experiment time: {remaining_time:.0f}s")

        # Check if we have enough time for a full cycle
        if remaining_time < ramp_duration + recovery_wait:
            print(f"⚠️ Not enough time for full cycle, stopping experiment")
            break

        # Perform one gradual memory stress cycle
        cycle_start = time.time()
        oom_triggered = perform_single_gradual_cycle(
            name=f"{name}-cycle-{cycle_count}",
            workers=workers,
            start_size=start_size,
            max_size=max_size,
            increment_mb=increment_mb,
            oom_score=oom_score,
            label_selectors=label_selectors,
            mode=mode,
            ns=ns,
            interval=interval,
            ramp_duration=ramp_duration,
            secrets=secrets
        )

        if oom_triggered:
            total_oom_events += 1
            print(f"💥 OOM Event #{total_oom_events} triggered!")

        cycle_duration = time.time() - cycle_start
        print(f"✅ Cycle #{cycle_count} completed in {cycle_duration:.0f}s")

        # Wait for pod recovery before next cycle
        remaining_time = total_duration - (time.time() - experiment_start)
        if remaining_time > recovery_wait:
            print(f"⏳ Waiting {recovery_wait}s for pod recovery...")
            time.sleep(recovery_wait)
        else:
            print(f"⏰ Experiment time ending, skipping recovery wait")
            break

    total_experiment_time = time.time() - experiment_start
    print(f"\n{'='*60}")
    print(f"🏁 REPEATED GRADUAL MEMORY STRESS COMPLETED!")
    print(f"{'='*60}")
    print(f"🔄 Total cycles performed: {cycle_count}")
    print(f"💥 Total OOM events: {total_oom_events}")
    print(f"⏱️  Total experiment time: {total_experiment_time:.0f}s")
    print(f"📊 Average cycle time: {total_experiment_time/cycle_count:.0f}s")

    return {
        "cycle_count": cycle_count,
        "oom_events": total_oom_events,
        "total_duration": total_experiment_time,
        "status": "completed",
        "target": label_selectors,
        "namespace": ns
    }

def perform_single_gradual_cycle(
    name: str,
    workers: int,
    start_size: str,
    max_size: str,
    increment_mb: int,
    oom_score: int,
    label_selectors: str,
    mode: str,
    ns: str,
    interval: int,
    ramp_duration: int,
    secrets: Secrets
) -> bool:
    """Perform one gradual memory stress cycle until OOM"""

    start_mb = int(start_size.replace("MB", "").replace("Mi", ""))
    max_mb = int(max_size.replace("MB", "").replace("Mi", ""))

    cycle_start = time.time()
    step_count = 0
    current_stress_name = None
    current_mb = start_mb
    oom_triggered = False

    print(f"📈 Starting gradual ramp: {start_size} → {max_size}")

    while time.time() - cycle_start < ramp_duration and current_mb <= max_mb:
        step_count += 1
        current_size = f"{current_mb}MB"

        print(f"  📊 Step {step_count}: {current_size}")

        try:
            # Clean previous stress
            if current_stress_name:
                try:
                    delete_stressor(current_stress_name, ns, secrets)
                    time.sleep(2)
                except Exception as e:
                    print(f"    ⚠️ Cleanup error: {e}")

            # Apply new stress level
            current_stress_name = f"{name}-step-{step_count}"

            stress_memory(
                name=current_stress_name,
                workers=workers,
                size=current_size,
                oom_score=oom_score,
                time_to_get_to_size="3s",
                ns=ns,
                label_selectors=label_selectors,
                mode=mode,
                duration=f"{interval + 10}s",
                secrets=secrets
            )
            print(f"    ✅ Applied {current_size} stress")

        except Exception as e:
            print(f"    ❌ Error at {current_size}: {e}")

        # Check if we're near the limit (likely to cause OOM)
        if current_mb >= max_mb * 0.8:
            print(f"    🔥 High memory pressure - OOM likely!")
            oom_triggered = True

        # Wait and increment
        elapsed = time.time() - cycle_start
        if elapsed < ramp_duration and current_mb < max_mb:
            time.sleep(interval)
            current_mb += increment_mb

    # Keep final stress for OOM
    print(f"  💥 Maintaining {current_mb}MB for OOM trigger...")
    time.sleep(15)

    # Cleanup
    if current_stress_name:
        try:
            delete_stressor(current_stress_name, ns, secrets)
        except Exception as e:
            print(f"    ⚠️ Final cleanup error: {e}")

    return oom_triggered

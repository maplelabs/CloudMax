import datetime
import json
import logging
import math
import random
import re
import time
from typing import List

from chaoslib.exceptions import ActivityFailed
from chaoslib.types import Secrets
from kubernetes import client, config, stream
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.stream.ws_client import ERROR_CHANNEL, STDERR_CHANNEL, STDOUT_CHANNEL

__all__ = ["restart_containers", "restart_containers_continuous"]
logger = logging.getLogger("chaostoolkit")


def restart_containers(
    label_selector: str = None,
    name_pattern: str = None,
    qty: int = 1,
    rand: bool = False,
    mode: str = "fixed",
    ns: str = "default",
    order: str = "alphabetic",
    container_name: str = None,
    restart_command: List[str] = None,
    secrets: Secrets = None,
):
    """
    Restart containers by sending signals to the main process (PID 1)
    """
    print("🔄 [DEBUG] Entered restart_containers()")
    
    api = None
    try:
        config.load_incluster_config()
        api = client.ApiClient()
        print("🔑 [DEBUG] Kubernetes API client created")
    except Exception as e:
        print(f"❌ [DEBUG] Failed to create k8s api client: {e}")
        raise

    v1 = client.CoreV1Api(api)

    print("🔍 [DEBUG] Selecting pods now...")
    pods = _select_pods(v1, label_selector, name_pattern, False, rand, mode, qty, ns, order)
    print(f"📋 [DEBUG] Pods selected: {len(pods)}")

    restarted_containers = []

    for pod in pods:
        pod_name = pod.metadata.name
        print(f"\n🎯 [DEBUG] Processing pod: {pod_name}")

        # container selection
        if container_name is None:
            try:
                names = [c.name for c in pod.spec.containers]
            except Exception as e:
                print(f"❌ [DEBUG] Failed to list containers for pod {pod_name}: {e}")
                restarted_containers.append({
                    "pod_name": pod_name,
                    "container_name": None,
                    "status": "failed",
                    "error": f"container list error: {e}"
                })
                continue

            print(f"   [DEBUG] Container candidates: {names}")
            selected_container = next((n for n in names if not re.search(r"(istio|linkerd|proxy)", n)), names[0])
            print(f"📦 [DEBUG] Auto-selected container: {selected_container}")
        else:
            selected_container = container_name
            print(f"📦 [DEBUG] Using provided container: {selected_container}")

        # initialize stdout/stderr to avoid UnboundLocalError
        stdout = None
        stderr = None
        ctrl_err = None

        try:
            before_count = _get_restart_count(v1, pod_name, ns, selected_container)
            print(f"📊 [DEBUG] Restart count before action: {before_count}")
        except Exception as e:
            print(f"❌ [DEBUG] Could not get restart count before action for {pod_name}: {e}")
            before_count = None

        # prepare strategies
        restart_strategies = [
            ["sh", "-c", "kill -INT 1"],     # SIGINT
            ["sh", "-c", "kill -2 1"],       # SIGINT by number
            ["sh", "-c", "kill -TERM 1"],    # SIGTERM fallback
            ["sh", "-c", "kill -9 1"],       # SIGKILL last resort
        ]
        if restart_command:
            restart_strategies.insert(0, restart_command)
            print(f"🔧 [DEBUG] Custom restart_command inserted: {restart_command}")

        print(f"🔧 [DEBUG] Restart strategies to try: {restart_strategies}")

        restart_successful = False

        for i, cmd in enumerate(restart_strategies):
            print(f"➡️ [DEBUG] Trying restart strategy #{i+1}: {' '.join(cmd)}")

            try:
                resp = stream.stream(
                    v1.connect_get_namespaced_pod_exec,
                    pod_name,
                    ns,
                    container=selected_container,
                    command=cmd,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )
                print("   [DEBUG] Exec stream opened successfully, running command...")
            except Exception as e:
                print(f"   ❌ [DEBUG] Failed to open exec stream for pod {pod_name}, container {selected_container}: {e}")
                # try next strategy
                continue

            try:
                # run_forever may raise, wrap
                resp.run_forever(timeout=10)
                print("   [DEBUG] run_forever returned/finished")
            except Exception as e:
                print(f"   ❌ [DEBUG] run_forever exception: {e}")

            # try to read channels; wrap in try so reading failures don't stop loop
            try:
                stdout = resp.read_channel(STDOUT_CHANNEL)
            except Exception as e:
                print(f"   ⚠️ [DEBUG] reading STDOUT channel failed: {e}")
                stdout = None

            try:
                stderr = resp.read_channel(STDERR_CHANNEL)
            except Exception as e:
                print(f"   ⚠️ [DEBUG] reading STDERR channel failed: {e}")
                stderr = None

            try:
                ctrl_err = resp.read_channel(ERROR_CHANNEL)
            except Exception as e:
                print(f"   ⚠️ [DEBUG] reading ERROR channel failed: {e}")
                ctrl_err = None

            print(f"   📤 [DEBUG] STDOUT (truncated): {stdout[:200] if stdout else stdout}")
            print(f"   📤 [DEBUG] STDERR (truncated): {stderr[:200] if stderr else stderr}")
            print(f"   📤 [DEBUG] CTRL_ERR: {ctrl_err}")

            # wait for restart to reflect in pod status
            print("   ⏳ [DEBUG] Waiting up to 60s for restart count to increment...")
            restart_verified = False
            deadline = time.time() + 60

            while time.time() < deadline:
                try:
                    current_count = _get_restart_count(v1, pod_name, ns, selected_container)
                except Exception as e:
                    print(f"   ⚠️ [DEBUG] Error getting restart count while polling: {e}")
                    current_count = None

                print(f"   [DEBUG] Polled restart count: {current_count} (before was {before_count})")

                if before_count is not None and current_count is not None and current_count > before_count:
                    print(f"   ✅ [DEBUG] Restart observed: {before_count} -> {current_count}")
                    restart_successful = True
                    restart_verified = True
                    break

                # small sleep to avoid hammering the API
                time.sleep(2)

            if restart_verified:
                print("   🎉 [DEBUG] Restart verified, breaking out of strategies loop")
                break
            else:
                print("   ⚠️ [DEBUG] This strategy did not result in a restart, going to next strategy if any")

        # after trying strategies
        if restart_successful:
            try:
                after_count = _get_restart_count(v1, pod_name, ns, selected_container)
            except Exception as e:
                print(f"❌ [DEBUG] Could not fetch restart count after success: {e}")
                after_count = None

            restarted_containers.append({
                "pod_name": pod_name,
                "container_name": selected_container,
                "status": "restart_verified",
                "before_count": before_count,
                "after_count": after_count,
                "stdout": stdout,
                "stderr": stderr,
                "ctrl_err": ctrl_err,
            })
            print(f"✅ [DEBUG] Restart recorded for {pod_name}: {before_count} -> {after_count}")
        else:
            print(f"❌ [DEBUG] All strategies exhausted for pod {pod_name} and no restart observed")
            restarted_containers.append({
                "pod_name": pod_name,
                "container_name": selected_container,
                "status": "restart_failed",
                "before_count": before_count,
                "stdout": stdout,
                "stderr": stderr,
                "ctrl_err": ctrl_err,
            })

    print(f"\n🏁 [DEBUG] restart_containers() finished. Processed {len(restarted_containers)} pods")
    return restarted_containers


def restart_containers_continuous(
    label_selector: str = None,
    name_pattern: str = None,
    qty: int = 1,
    rand: bool = False,
    mode: str = "fixed",
    ns: str = "default",
    order: str = "alphabetic",
    container_name: str = None,
    restart_command: List[str] = None,
    interval: int = 30,
    duration: int = 300,
    secrets: Secrets = None,
):
    print("🚀 [DEBUG] Entered restart_containers_continuous()")
    print(f"   Params => label_selector={label_selector}, interval={interval}, duration={duration}, ns={ns}, container_name={container_name}")

    start_time = time.time()
    restart_count = 0
    total_containers_restarted = 0

    while time.time() - start_time < duration:
        restart_count += 1
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*60}")
        print(f"🔄 [DEBUG] Container Restart Cycle #{restart_count} at {current_time}")
        print(f"{'='*60}")

        try:
            result = restart_containers(
                label_selector=label_selector,
                name_pattern=name_pattern,
                qty=qty,
                rand=rand,
                mode=mode,
                ns=ns,
                order=order,
                container_name=container_name,
                restart_command=restart_command,
                secrets=secrets,
            )
            print(f"   [DEBUG] restart_containers returned {len(result)} entries")
        except Exception as e:
            print(f"❌ [DEBUG] Exception calling restart_containers in cycle #{restart_count}: {e}")
            result = []

        successful_restarts = [r for r in result if r.get("status") == "restart_verified"]
        failed_restarts = [r for r in result if r.get("status") != "restart_verified"]

        total_containers_restarted += len(successful_restarts)

        print(f"✅ [DEBUG] Successfully restarted this cycle: {len(successful_restarts)}")
        if failed_restarts:
            print(f"❌ [DEBUG] Failed restarts this cycle: {len(failed_restarts)}")
            for fr in failed_restarts:
                print(f"   - {fr.get('pod_name')} status={fr.get('status')} details={fr}")

        for restart_info in successful_restarts:
            print(f"   📦 [DEBUG] {restart_info.get('pod_name')}: {restart_info.get('status')}")

        # Compute remaining time
        elapsed = time.time() - start_time
        remaining = duration - elapsed

        if remaining <= interval:
            print(f"⏰ [DEBUG] Less than {interval} seconds remaining ({remaining:.0f}s). Stopping continuous run.")
            break

        print(f"⏳ [DEBUG] Waiting {interval} seconds until next cycle. Time remaining: {remaining:.0f}s")
        time.sleep(interval)

    total_duration = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"🏁 [DEBUG] Continuous restart experiment completed")
    print(f"📈 Total cycles: {restart_count}")
    print(f"📦 Total containers restarted: {total_containers_restarted}")
    print(f"⏱️ Total duration: {total_duration:.0f} seconds")
    print(f"📊 Average cycle time: { (total_duration / restart_count) if restart_count else 0:.1f} seconds")

    return {
        "restart_cycles": restart_count,
        "total_containers_restarted": total_containers_restarted,
        "duration": total_duration,
        "status": "completed",
        "target": label_selector,
        "namespace": ns,
        "container_name": container_name,
    }


def _select_pods(
    v1,
    label_selector: str = None,
    name_pattern: str = None,
    all: bool = False,
    rand: bool = False,
    mode: str = "fixed",
    qty: int = 1,
    ns: str = "default",
    order: str = "alphabetic",
):
    """
    Select pods based on the given criteria.
    """
    print("🔍 [DEBUG] Entered _select_pods()")
    print(f"   Params => label_selector={label_selector}, name_pattern={name_pattern}, all={all}, rand={rand}, mode={mode}, qty={qty}, ns={ns}, order={order}")

    try:
        if label_selector:
            print(f"   [DEBUG] Listing pods with label_selector={label_selector}")
            ret = v1.list_namespaced_pod(namespace=ns, label_selector=label_selector)
        else:
            print("   [DEBUG] Listing all pods in namespace")
            ret = v1.list_namespaced_pod(namespace=ns)
    except Exception as e:
        print(f"❌ [DEBUG] Error listing pods in namespace {ns}: {e}")
        return []

    pods = ret.items or []
    print(f"📋 [DEBUG] Found {len(pods)} pods initially")

    if name_pattern:
        try:
            pattern = re.compile(name_pattern)
            pods = [p for p in pods if pattern.search(p.metadata.name)]
            print(f"🔍 [DEBUG] After name pattern filter: {len(pods)} pods")
        except re.error as e:
            print(f"❌ [DEBUG] Invalid name_pattern regex: {e}")
            return []

    if not pods:
        print("⚠️ [DEBUG] No pods found matching criteria")
        return []

    if order == "oldest":
        try:
            pods.sort(key=_sort_by_pod_creation_timestamp)
            print("   [DEBUG] Pods sorted by oldest first")
        except Exception as e:
            print(f"⚠️ [DEBUG] Error sorting pods by creation timestamp: {e}")

    if all:
        print("📌 [DEBUG] Returning all matching pods")
        return pods

    if mode == "percentage":
        try:
            qty = int(math.ceil((qty / 100.0) * len(pods)))
            print(f"📊 [DEBUG] Percentage mode selected, selecting {qty} pods")
        except Exception as e:
            print(f"⚠️ [DEBUG] Error calculating percentage qty: {e}")

    if rand:
        try:
            pods = random.sample(pods, min(qty, len(pods)))
            print(f"🎲 [DEBUG] Random selection chosen: {len(pods)} pods")
        except ValueError as e:
            print(f"⚠️ [DEBUG] Random selection error: {e}")
            pods = pods[:qty]
    else:
        pods = pods[:qty]
        print(f"📝 [DEBUG] Sequential selection: {len(pods)} pods")

    selected_names = [p.metadata.name for p in pods]
    print(f"✅ [DEBUG] Selected pods: {selected_names}")
    return pods


def _sort_by_pod_creation_timestamp(pod: V1Pod) -> datetime.datetime:
    """
    Key function for sorting pods by creation timestamp.
    """
    ts = pod.metadata.creation_timestamp
    print(f"   [DEBUG] Pod {pod.metadata.name} creationTimestamp: {ts}")
    return ts


def _get_restart_count(v1, pod_name: str, ns: str, container_name: str) -> int:
    """Get the restart count for a specific container in a pod."""
    print(f"🔍 [DEBUG] _get_restart_count() called for pod={pod_name}, ns={ns}, container={container_name}")
    try:
        pod_status = v1.read_namespaced_pod_status(pod_name, ns)
    except Exception as e:
        print(f"❌ [DEBUG] Failed to read pod status for {pod_name} in {ns}: {e}")
        raise

    container_statuses = pod_status.status.container_statuses or []
    print(f"   [DEBUG] Found {len(container_statuses)} container_status entries")
    for container_status in container_statuses:
        name = getattr(container_status, "name", None)
        rc = getattr(container_status, "restart_count", None)
        print(f"   [DEBUG] container: {name}, restart_count: {rc}")
        if name == container_name:
            print(f"   ✅ [DEBUG] Matched container {name}, restart_count={rc}")
            return rc
    print("   ⚠️ [DEBUG] Container name not found in pod status, returning None")
    return None

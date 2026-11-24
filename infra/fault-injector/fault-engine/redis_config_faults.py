import subprocess
import time
from kubernetes import client, config

def get_redis_pod_name(pod_label="user-timeline-redis", namespace="default"):
    """Get Redis pod name with better error handling"""
    try:
        # Try Kubernetes API first
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"app={pod_label}"
        )
        
        if pods.items:
            for pod in pods.items:
                if pod.status.phase == "Running":
                    print(f"✅ Found Redis pod: {pod.metadata.name}")
                    return pod.metadata.name
            
            # If no running pods, return first pod
            pod_name = pods.items[0].metadata.name
            print(f"⚠️ Found non-running Redis pod: {pod_name}")
            return pod_name
        else:
            # Fallback: try different label patterns
            common_redis_labels = [
                f"app={pod_label}",
                f"app.kubernetes.io/name={pod_label}",
                "app=redis",
                "app.kubernetes.io/name=redis",
                "component=redis"
            ]
            
            for label in common_redis_labels:
                pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label)
                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    print(f"✅ Found Redis pod with label '{label}': {pod_name}")
                    return pod_name
            
            # ✅ FIXED: Fallback kubectl now includes namespace
            print(f"⚠️ No pods found via API, falling back to kubectl for namespace '{namespace}'")
            try:
                cmd = (
                    f"kubectl get pod -n {namespace} -l app={pod_label} "
                    f"-o jsonpath='{{.items[0].metadata.name}}'"
                )
                pod_name = subprocess.check_output(cmd, shell=True, text=True).strip()
                if pod_name:
                    print(f"✅ Found Redis pod via kubectl: {pod_name}")
                    return pod_name
            except subprocess.CalledProcessError as e:
                print(f"❌ kubectl fallback failed: {e}")

            # List all pods to help debug
            all_pods = v1.list_namespaced_pod(namespace=namespace)
            print(f"❌ No Redis pods found. Available pods in {namespace}:")
            for pod in all_pods.items:
                print(f"  - {pod.metadata.name} (labels: {pod.metadata.labels})")
            
            raise Exception(f"No Redis pods found with any common labels in namespace {namespace}")
            
    except Exception as e:
        print(f"❌ Error finding Redis pod: {e}")
        raise

def redis_exec_command(pod_label, redis_command, namespace="default"):
    """Executes a redis-cli command with better error handling"""
    try:
        pod_name = get_redis_pod_name(pod_label, namespace)
        
        # Use Kubernetes API for exec
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        v1 = client.CoreV1Api()
        
        # Execute command in pod
        from kubernetes.stream import stream
        
        exec_command = ["redis-cli"] + redis_command.split()
        
        resp = stream(
            v1.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=exec_command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )
        
        print(f"[CMD] {redis_command} → {resp.strip()}")
        return resp.strip()
        
    except Exception as e:
        print(f"❌ Failed to execute Redis command: {e}")
        # Fallback to kubectl if K8s API fails
        try:
            full_cmd = f"kubectl exec {pod_name} -n {namespace} -- redis-cli {redis_command}"
            output = subprocess.check_output(full_cmd, shell=True, text=True)
            print(f"[CMD] {redis_command} → {output.strip()}")
            return output.strip()
        except subprocess.CalledProcessError as kubectl_error:
            print(f"❌ kubectl fallback also failed: {kubectl_error}")
            raise

def redis_memory_stress_test(pod_label="user-timeline-redis", namespace="default", 
                             limit_in_kb=100, eviction_policy="noeviction", duration=240):
    """Set Redis maxmemory and policy with namespace support"""
    print(f"🚀 Starting Redis memory stress test")
    print(f"📍 Namespace: {namespace}")
    print(f"🏷️  Pod label: {pod_label}")
    
    try:
        redis_exec_command(pod_label, f"CONFIG SET maxmemory {limit_in_kb}kb", namespace)
        redis_exec_command(pod_label, f"CONFIG SET maxmemory-policy {eviction_policy}", namespace)

        print(f"[INFO] Set maxmemory={limit_in_kb}KB, policy={eviction_policy}")
        print(f"[INFO] Sleeping for {duration} seconds for stress effect...")
        time.sleep(duration)

        return reset_maxmemory(pod_label, namespace)
    except Exception as e:
        print(f"❌ Redis stress test failed: {e}")
        return {"status": "error", "error": str(e)}

def reset_maxmemory(pod_label="user-timeline-redis", namespace="default"):
    """Reset Redis memory settings with namespace support"""
    try:
        redis_exec_command(pod_label, "CONFIG SET maxmemory 0", namespace)
        redis_exec_command(pod_label, "CONFIG SET maxmemory-policy noeviction", namespace)
        print("[INFO] Redis settings reset to default.")
        return {"status": "reset"}
    except Exception as e:
        print(f"❌ Failed to reset Redis settings: {e}")
        return {"status": "error", "error": str(e)}

def discover_redis_pods(namespace="default"):
    """Discover all Redis-like pods in the namespace"""
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config()
    
    v1 = client.CoreV1Api()
    all_pods = v1.list_namespaced_pod(namespace=namespace)
    
    redis_pods = []
    for pod in all_pods.items:
        pod_name = pod.metadata.name.lower()
        labels = pod.metadata.labels or {}
        
        # Check if pod name or labels suggest it's Redis
        if any(keyword in pod_name for keyword in ['redis', 'cache']) or \
           any('redis' in str(v).lower() for v in labels.values()):
            redis_pods.append({
                'name': pod.metadata.name,
                'labels': labels,
                'status': pod.status.phase
            })
    
    print(f"🔍 Found {len(redis_pods)} Redis-like pods:")
    for pod in redis_pods:
        print(f"  - {pod['name']} ({pod['status']}) - labels: {pod['labels']}")
    
    return redis_pods

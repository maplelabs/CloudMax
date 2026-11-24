"""
Kubernetes actions for Chaos Toolkit experiments
Uses Kubernetes Python client to execute commands in pods
"""
 
from kubernetes import client, config
from kubernetes.stream import stream
import time
import logging
 
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
def load_k8s_config():
    """Load Kubernetes configuration"""
    try:
        # Try to load in-cluster config first (if running in a pod)
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except:
        # Fall back to local kubeconfig
        config.load_kube_config()
        logger.info("Loaded local Kubernetes config")

def get_pod_name_by_deployment(namespace, deployment_name):
    """Get the first running pod name for a deployment"""
    load_k8s_config()
    v1 = client.CoreV1Api()

    # Get pods with deployment label
    label_selector = f"app={deployment_name}"
    pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)   

    for pod in pods.items:
        if pod.status.phase == "Running":
            logger.info(f"Found running pod: {pod.metadata.name} for deployment: {deployment_name}")
            return pod.metadata.name

    raise Exception(f"No running pods found for deployment: {deployment_name}")

def execute_command_in_pod(namespace, deployment_name, container_name, command):        
    """Execute a command in a specific container of a pod"""
    load_k8s_config()
    v1 = client.CoreV1Api()

    # Get pod name
    pod_name = get_pod_name_by_deployment(namespace, deployment_name)

    logger.info(f"Executing command in pod {pod_name}, container {container_name}: {' '.join(command)}")

    try:
        # Execute the command
        resp = stream(
            v1.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=command,
            container=container_name,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )

        logger.info(f"Command executed successfully. Output: {resp}")
        return {"status": "success", "output": resp, "pod": pod_name}

    except Exception as e:
        logger.error(f"Failed to execute command: {e}")
        return {"status": "error", "error": str(e), "pod": pod_name}

# Specific functions for social network cleanup

def clear_redis_data(namespace="default", deployment_name="social-graph-redis", container_name="social-graph-redis"):
    """Clear all data from Redis"""
    return execute_command_in_pod(
        namespace=namespace,
        deployment_name=deployment_name,
        container_name=container_name,
        command=["redis-cli", "FLUSHALL"]
    )

def clear_memcached_data(namespace="default", deployment_name="post-storage-memcached", container_name="post-storage-memcached"):
    """Clear all data from Memcached"""
    return execute_command_in_pod(
        namespace=namespace,
        deployment_name=deployment_name,
        container_name=container_name,
        command=["sh", "-c", "echo 'flush_all' | nc localhost 11211"]
    )

def drop_mongodb_database(namespace="default", deployment_name="post-storage-mongodb",  
                         container_name="post-storage-mongodb", database_name="post"):  
    """Drop a MongoDB database"""
    mongo_command = f"db.getSiblingDB('{database_name}').dropDatabase()"
    result1 = execute_command_in_pod(
        namespace=namespace,
        deployment_name=deployment_name,
        container_name=container_name,
        command=["mongo", "--eval", mongo_command]
    )

    # Also drop the ransomware database if it exists
    ransomware_command = "db.getSiblingDB('READ__ME_TO_RECOVER_YOUR_DATA').dropDatabase()"
    result2 = execute_command_in_pod(
        namespace=namespace,
        deployment_name=deployment_name,
        container_name=container_name,
        command=["mongo", "--eval", ransomware_command]
    )

    # Return success if either operation succeeded (main database drop is most important)
    return result1

# Convenience functions for social network reset

def reset_social_graph_redis(namespace="default"):
    """Reset social graph Redis data"""
    return clear_redis_data(namespace, "social-graph-redis", "social-graph-redis")      

def reset_home_timeline_redis(namespace="default"):
    """Reset home timeline Redis data"""
    return clear_redis_data(namespace, "home-timeline-redis", "home-timeline-redis")    

def reset_user_timeline_redis(namespace="default"):
    """Reset user timeline Redis data"""
    return clear_redis_data(namespace, "user-timeline-redis", "user-timeline-redis")    

def reset_post_storage_memcached(namespace="default"):
    """Reset post storage Memcached data"""
    return clear_memcached_data(namespace, "post-storage-memcached", "post-storage-memcached")

def reset_user_memcached(namespace="default"):
    """Reset user Memcached data"""
    return clear_memcached_data(namespace, "user-memcached", "user-memcached")

def reset_post_database(namespace="default"):
    """Reset post MongoDB database"""
    return drop_mongodb_database(namespace, "post-storage-mongodb", "post-storage-mongodb", "post")

def reset_user_database(namespace="default"):
    """Reset user MongoDB database"""
    return drop_mongodb_database(namespace, "user-mongodb", "user-mongodb", "user")     

def reset_social_graph_database(namespace="default"):
    """Reset social graph MongoDB database"""
    return drop_mongodb_database(namespace, "social-graph-mongodb", "social-graph-mongodb", "social-graph")

def reset_user_timeline_database(namespace="default"):
    """Reset user timeline MongoDB database"""
    return drop_mongodb_database(namespace, "user-timeline-mongodb", "user-timeline-mongodb", "user-timeline")

def full_social_network_reset(namespace="default"):
    """Perform a complete reset of all social network data"""
    results = {}

    logger.info("Starting full social network reset...")

    # Clear all Redis instances
    logger.info("Clearing Redis data...")
    results["social_graph_redis"] = reset_social_graph_redis(namespace)
    results["home_timeline_redis"] = reset_home_timeline_redis(namespace)
    results["user_timeline_redis"] = reset_user_timeline_redis(namespace)

    # Clear all Memcached instances
    logger.info("Clearing Memcached data...")
    results["post_storage_memcached"] = reset_post_storage_memcached(namespace)
    results["user_memcached"] = reset_user_memcached(namespace)

    # Drop all MongoDB databases
    logger.info("Dropping MongoDB databases...")
    results["post_database"] = reset_post_database(namespace)
    results["user_database"] = reset_user_database(namespace)
    results["social_graph_database"] = reset_social_graph_database(namespace)
    results["user_timeline_database"] = reset_user_timeline_database(namespace)

    logger.info("Full social network reset completed")
    return results

def reinitialize_social_network(ip="4.154.253.199", port="8080", include_posts=True):   
    """Reinitialize social network data using the init script"""
    import subprocess
    import os

    logger.info("Reinitializing social network data...")

    # Change to the socialNetwork directory
    script_dir = "socialNetwork"
    if not os.path.exists(script_dir):
        return {"status": "error", "error": "socialNetwork directory not found"}        

    # Prepare command
    command = ["python3", "scripts/init_social_graph.py", "--ip", ip, "--port", port]   

    if include_posts:
        command.append("--compose")

    try:
        # Execute the init script
        result = subprocess.run(
            command,
            cwd="socialNetwork",
            capture_output=True,
            text=True,
            #timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            logger.info("Social network reinitialization completed successfully")       
            return {"status": "success", "output": result.stdout}
        else:
            logger.error(f"Reinitialization failed: {result.stderr}")
            return {"status": "error", "error": result.stderr}

    except subprocess.TimeoutExpired:
        logger.error("Reinitialization timed out")
        return {"status": "error", "error": "Initialization script timed out"}
    except Exception as e:
        logger.error(f"Reinitialization failed: {e}")
        return {"status": "error", "error": str(e)}


def complete_reset_and_reinit(namespace="default", ip="4.154.253.199", port="8080", include_posts=True):
    """Complete reset and reinitialization of social network"""
    logger.info("Starting complete reset and reinitialization...")

    # Step 1: Reset all data

    reset_results = full_social_network_reset(namespace)

    # Wait a bit for cleanup to complete
    time.sleep(5)

    # Step 2: Restart core services
    restart_results = restart_core_services(namespace)

    # Step 2: Reinitialize
    init_results = reinitialize_social_network(ip, port, include_posts)

    return {
        "reset_results": reset_results,
        "init_results": init_results
    }

def restart_core_services(namespace="default"):
    """Restart core microservices after database reset"""
    load_k8s_config()
    apps_v1 = client.AppsV1Api()

    # List of core services to restart
    core_services = [
        "social-graph-service",
        "user-service",
        "post-storage-service",
        "compose-post-service",
        "home-timeline-service",
        "user-timeline-service",
        "nginx-thrift",
        "text-service",
        "unique-id-service",
        "user-mention-service"
    ]

    restart_results = {}

    for service in core_services:
        try:
            logger.info(f"Restarting deployment: {service}")

            # Get the deployment
            deployment = apps_v1.read_namespaced_deployment(name=service, namespace=namespace)

            # Update the deployment to trigger restart (add/update restart annotation)  
            if deployment.spec.template.metadata.annotations is None:
                deployment.spec.template.metadata.annotations = {}

            deployment.spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = str(int(time.time()))

            # Apply the update
            apps_v1.patch_namespaced_deployment(
                name=service,
                namespace=namespace,
                body=deployment
            )

            restart_results[service] = "success"
            logger.info(f"✅ Successfully restarted {service}")

        except Exception as e:
            restart_results[service] = f"error: {str(e)}"
            logger.error(f"❌ Failed to restart {service}: {str(e)}")

    # Wait for services to start up
    logger.info("Waiting 180 seconds for services to restart...")
    time.sleep(180)

    return restart_results

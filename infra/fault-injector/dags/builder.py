import os
import json
import glob
from datetime import datetime
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

FAULTS_DIR = "/opt/airflow/faults"  # Path inside Airflow container (for reading configs)
HOST_FAULTS_DIR = os.environ.get("HOST_FAULTS_DIR", "/opt/airflow/faults")  # Path on HOST (from env var)
HOST_FAULT_ENGINE_DIR = os.environ.get("HOST_FAULT_ENGINE_DIR", "/opt/airflow/fault-engine")  # Python modules on HOST (from env var)
DEFAULT_IMAGE = "priyanshu01ce/airflow_chaos:latest"
CONTAINER_FAULT_DIR = "/app/faults"  # Where faults will be visible in chaos container
CONTAINER_FAULT_ENGINE_DIR = "/app/fault-engine"  # Where Python modules will be visible in chaos container

print("⚡ Loading DockerOperator-based DAG generator")

def create_dag_from_config(config_file_path):
    with open(config_file_path, 'r') as f:
        config = json.load(f)

    dag_id = config.get("dag_id")
    if not dag_id:
        print(f"Skipping {config_file_path}: Missing 'dag_id'")
        return None, None

    task_id = config.get("task_id", f"run_{dag_id}")
    experiment_json = config.get("experiment_json")
    if not experiment_json:
        print(f"Skipping {dag_id}: Missing experiment_json field")
        return None, None

    dag_tags = config.get("tags", ["chaos", "docker"])
    dag_description = config.get("description", f"Chaos experiment: {experiment_json}")
    dag_schedule = config.get("schedule", "@once")

    default_args = {
        "owner": "airflow",
        "depends_on_past": False,
        "start_date": datetime(2025, 1, 1),
    }

    dag = DAG(
        dag_id=dag_id,
        default_args=default_args,
        schedule=dag_schedule,
        tags=dag_tags,
        catchup=False,
        description=dag_description,
    )

    experiment_container_path = f"{CONTAINER_FAULT_DIR}/{experiment_json}"

    # Corrected DockerOperator
    run_fault = DockerOperator(
        task_id=task_id,
        image=DEFAULT_IMAGE,
        api_version="auto",
        auto_remove=True,
        network_mode="host",
        user="root",  # Required to access Docker socket
        # Mount host folder, fault-engine, and Docker socket to container
        mounts=[
            {
                "Source": HOST_FAULTS_DIR,
                "Target": CONTAINER_FAULT_DIR,
                "Type": "bind",
            },
            {
                "Source": HOST_FAULT_ENGINE_DIR,
                "Target": CONTAINER_FAULT_ENGINE_DIR,
                "Type": "bind",
            },
            {
                "Source": "/var/run/docker.sock",
                "Target": "/var/run/docker.sock",
                "Type": "bind",
            }
        ],
        command=f"""bash -c "
            export PYTHONPATH={CONTAINER_FAULT_DIR}:{CONTAINER_FAULT_ENGINE_DIR}:$PYTHONPATH &&
            echo '📄 Listing experiments:' &&
            ls -la {CONTAINER_FAULT_DIR} &&
            echo '📄 Showing experiment file:' &&
            cat {experiment_container_path} &&
            echo '🚀 Running chaos experiment:' &&
            chaos run {experiment_container_path}
        " """,
        docker_url="unix://var/run/docker.sock",
        dag=dag,
    )

    return dag_id, dag


# -------- Load all fault JSON configs --------
config_files = glob.glob(os.path.join(FAULTS_DIR, "*.json"))
print(f"Found {len(config_files)} JSON fault files in {FAULTS_DIR}")

for config_file_path in config_files:
    try:
        dag_id, dag = create_dag_from_config(config_file_path)
        if dag_id and dag:
            globals()[dag_id] = dag
            print(f"✔ Loaded DAG: {dag_id}")
        else:
            print(f"⚠ Skipped: {config_file_path}")
    except Exception as exc:
        print(f"❌ Failed loading {config_file_path}: {exc}")

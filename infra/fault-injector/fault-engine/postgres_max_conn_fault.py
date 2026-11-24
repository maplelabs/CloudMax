import psycopg2
import subprocess
import time
import threading

DB_USER = "postgres"
DB_PASSWORD = "password"
DB_NAME = "hotel_booking_db"
DB_HOST = "localhost"
DB_PORT = 5432
DOCKER_CONTAINER = "hotel_postgres"

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ----------------------------
# Alter max_connections
# ----------------------------
def set_max_connections(max_conn=50):
    """Set max_connections via ALTER SYSTEM"""
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                            host=DB_HOST, port=DB_PORT)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"ALTER SYSTEM SET max_connections = {max_conn};")
    conn.close()
    log(f"✅ max_connections set to {max_conn}")

def restore_max_connections(default_conn=100):
    """Restore max_connections to default value"""
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                            host=DB_HOST, port=DB_PORT)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"ALTER SYSTEM SET max_connections = {default_conn};")
    conn.close()
    log(f"✅ max_connections restored to {default_conn}")

# ----------------------------
# Restart Postgres Docker
# ----------------------------
def restart_postgres(container_name=DOCKER_CONTAINER):
    log(f"🔄 Restarting Postgres container: {container_name}")
    try:
        subprocess.run(["docker", "restart", container_name], check=True)
        log("✅ Postgres restarted successfully")
        time.sleep(5)
    except subprocess.CalledProcessError as e:
        log(f"❌ Failed to restart Postgres: {e}")

# ----------------------------
# Simulate maxed-out connections
# ----------------------------
def open_connection(thread_id, hold_time=5):
    try:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                                host=DB_HOST, port=DB_PORT)
        log(f"➡️ Thread {thread_id} opened connection")
        time.sleep(hold_time)
        conn.close()
        log(f"✅ Thread {thread_id} closed connection")
    except Exception as e:
        log(f"⚠️ Thread {thread_id} failed to connect: {e}")

def simulate_max_connections(max_conn, hold_time=5):
    log(f"🔹 Starting {max_conn} simultaneous connections")
    threads = []
    for i in range(max_conn):
        t = threading.Thread(target=open_connection, args=(i, hold_time))
        t.start()
        threads.append(t)
        time.sleep(0.01)

    for t in threads:
        t.join()
    log(f"✅ All {max_conn} connections completed")

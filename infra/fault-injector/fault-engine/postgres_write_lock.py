import time
import psycopg2
 
DB_USER = "postgres"
DB_PASSWORD = "password"
DB_NAME = "hotel_booking_db"
DB_HOST = "localhost"
DB_PORT = 5433
 
lock_conn = None
 
 
def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
 
 
def _set_lock_timeout(timeout_ms):
    """
    Set lock_timeout globally so blocked queries fail instead of waiting.
    timeout_ms: timeout in milliseconds (0 = disabled/wait forever)
    """
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.autocommit = True
        cur = conn.cursor()
 
        cur.execute(f"ALTER SYSTEM SET lock_timeout = '{timeout_ms}ms';")
        cur.execute("SELECT pg_reload_conf();")
 
        conn.close()
        log(f"⚙️  lock_timeout set to {timeout_ms}ms globally")
        return True
    except Exception as e:
        log(f"❌ Failed to set lock_timeout: {str(e)}")
        return False
 
 
# ============================================================
# SHARE ROW EXCLUSIVE LOCK MANAGEMENT
# ============================================================
 
def acquire_write_lock(lock_duration_sec=150, lock_timeout_ms=5000):
    """
    Acquires SHARE ROW EXCLUSIVE lock:
    - SELECT allowed
    - INSERT / UPDATE / DELETE blocked (will FAIL with timeout, not wait)
 
    Args:
        lock_duration_sec: How long to hold the lock
        lock_timeout_ms: Timeout for blocked queries (default 5000ms = 5 seconds)
                        Blocked queries will FAIL after this timeout instead of waiting
    """
    global lock_conn
 
    try:
        # Step 1: Set lock_timeout so blocked queries FAIL instead of waiting
        log(f"⚙️  Setting lock_timeout to {lock_timeout_ms}ms (blocked queries will FAIL after this)")
        _set_lock_timeout(lock_timeout_ms)
 
        # Step 2: Connect and acquire the lock
        lock_conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
 
        lock_conn.autocommit = False
        cur = lock_conn.cursor()
 
        # Disable lock_timeout for THIS connection so we can acquire the lock
        cur.execute("SET lock_timeout = 0;")
 
        log("🔒 Acquiring SHARE ROW EXCLUSIVE lock on booking_details...")
        cur.execute("BEGIN;")
        cur.execute("LOCK TABLE booking_details IN SHARE ROW EXCLUSIVE MODE;")
 
        log("✅ Lock acquired. SELECT allowed, INSERT/UPDATE/DELETE will FAIL with timeout.")
        log(f"⏱  Holding lock for {lock_duration_sec} seconds...")
        log(f"⚠️  Any INSERT/UPDATE/DELETE on booking_details will timeout after {lock_timeout_ms}ms")
 
        time.sleep(lock_duration_sec)
 
        log("🔓 Releasing lock (COMMIT)...")
        lock_conn.commit()
 
        # Step 3: Reset lock_timeout to default (disabled)
        log("⚙️  Resetting lock_timeout to default (disabled)")
        _set_lock_timeout(0)
 
        return {
            "status": "success",
            "message": f"SHARE ROW EXCLUSIVE lock held for {lock_duration_sec}s. Blocked queries failed with {lock_timeout_ms}ms timeout."
        }
 
    except Exception as e:
        log(f"❌ Error during lock execution: {str(e)}")
        if lock_conn:
            lock_conn.rollback()
        # Reset lock_timeout even on failure
        _set_lock_timeout(0)
        return {
            "status": "failed",
            "error": str(e)
        }
 
 
def release_write_lock():
    """
    Safety rollback if lock is still held.
    Also resets lock_timeout to default.
    """
    global lock_conn
 
    try:
        if lock_conn:
            log("🔄 Forcing rollback to release lock...")
            lock_conn.rollback()
            lock_conn.close()
            lock_conn = None
 
        # Always reset lock_timeout to default
        log("⚙️  Resetting lock_timeout to default (disabled)")
        _set_lock_timeout(0)
 
        return {
            "status": "success",
            "message": "Lock released (if held) and lock_timeout reset"
        }
 
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }
 
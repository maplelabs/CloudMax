import threading
import time
import random
import requests
import psycopg2
from psycopg2 import sql, OperationalError
 
DB_USER = "postgres"
DB_PASSWORD = "password"
DB_NAME = "hotel_booking_db"
DB_HOST = "localhost"
DB_PORT = 5433
 
def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
 
# ============================================================
# STATEMENT_TIMEOUT MANAGEMENT
# ============================================================
 
def set_statement_timeout(timeout_ms=50):
    """Enable statement_timeout for all sessions using ALTER SYSTEM."""
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT
    )
    conn.autocommit = True
 
    with conn.cursor() as cur:
        cur.execute(f"ALTER SYSTEM SET statement_timeout = '{timeout_ms}ms';")
        cur.execute("SELECT pg_reload_conf();")
 
    conn.close()
    log(f"✅ statement_timeout set to {timeout_ms}ms")
    time.sleep(150)
 
 
def restore_statement_timeout():
    """Restore statement_timeout back to unlimited."""
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT
    )
    conn.autocommit = True
 
    with conn.cursor() as cur:
        cur.execute("ALTER SYSTEM SET statement_timeout = '0';")
        cur.execute("SELECT pg_reload_conf();")
 
    conn.close()
    log("🔄 statement_timeout restored to unlimited")
 
def set_statement_timeout_fault(api_url: str):
    """
    Activates the Postgres statement timeout fault flag
    using the backend fault-injector API.
    """
 
    print(f"Calling API: {api_url}")
 
    try:
        response = requests.put(api_url, timeout=10)
        response.raise_for_status()
 
        print("✅ Postgres statement_timeout fault activated.")
        print("⏱ Sleeping for 300 seconds while fault stays active...")
        time.sleep(5)
 
        return {
            "status": "success",
            "message": "statement_timeout fault activated"
        }
 
    except Exception as e:
        print(f"❌ Failed to activate statement_timeout fault: {str(e)}")
 
        return {
            "status": "failed",
            "error": str(e)
        }
 
def reset_statement_timeout_fault(api_url: str):
    """
    Resets the Postgres statement_timeout fault flag
    using the backend fault-injector API.
    """
 
    print(f"Calling API to reset fault: {api_url}")
 
    try:
        response = requests.put(api_url, timeout=10)
        response.raise_for_status()
 
        print("🔄 Postgres statement_timeout fault reset.")
 
        return {
            "status": "success",
            "message": "statement_timeout fault reset"
        }
 
    except Exception as e:
        print(f"❌ Failed to reset statement_timeout fault: {str(e)}")
 
        return {
            "status": "failed",
            "error": str(e)
        }
 
 
# # ============================================================
# # SIMULATING SLOW QUERIES TO TRIGGER STATEMENT TIMEOUT
# # ============================================================
 
# def simulate_slow_query(thread_id, table, timeout_ms):
#     conn = None
#     cursor = None
 
#     try:
#         conn = psycopg2.connect(
#             dbname=DB_NAME,
#             user=DB_USER,
#             password=DB_PASSWORD,
#             host=DB_HOST,
#             port=DB_PORT
#         )
#         conn.autocommit = False
#         cursor = conn.cursor()
 
#         log(f"➡️ Thread {thread_id} starting slow SELECT on {table}")
 
#         # Force slow statement using pg_sleep
#         sleep_seconds = (timeout_ms / 1000) + 0.2
#         log(f"   ⏳ Thread {thread_id} running SELECT pg_sleep({sleep_seconds})")
 
#         # No table name needed here
#         cursor.execute("SELECT pg_sleep(%s);", [sleep_seconds])
 
#         conn.commit()
#         log(f"❗ Thread {thread_id}: Query unexpectedly succeeded (should have timed out)")
 
#     except OperationalError as e:
#         log(f"⚠️ Thread {thread_id} OperationalError: {e}")
#         if conn:
#             conn.rollback()
 
#     except Exception as e:
#         log(f"⚠️ Thread {thread_id} failed: {e}")
#         if conn:
#             conn.rollback()
 
#     finally:
#         if cursor:
#             cursor.close()
#         if conn:
#             conn.close()
 
 
# def simulate_statement_timeout_fault(table="chaos_statement_test",
#                                      num_threads=5,
#                                      timeout_ms=50):
 
#     # Ensure table exists
#     conn = psycopg2.connect(
#         dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
#         host=DB_HOST, port=DB_PORT
#     )
#     with conn.cursor() as cur:
#         cur.execute(f"CREATE TABLE IF NOT EXISTS {table} (id serial, val text);")
#     conn.commit()
#     conn.close()
 
#     log(f"🔹 Starting {num_threads} slow queries to trigger statement_timeout on '{table}'")
 
#     threads = []
#     for i in range(num_threads):
#         t = threading.Thread(
#             target=simulate_slow_query,
#             args=(i, table, timeout_ms)
#         )
#         t.start()
#         threads.append(t)
#         time.sleep(0.05)
 
#     for t in threads:
#         t.join()
 
#     log(f"🏁 Completed all {num_threads} slow queries (most should have timed out)")

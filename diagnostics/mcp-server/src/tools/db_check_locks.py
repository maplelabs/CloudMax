"""Tool 3: db.checkWriteLocks - Check if database has pending write locks."""
import asyncio
import logging
from typing import List

import psycopg2
from psycopg2 import OperationalError

from ..config.settings import settings
from ..models.postgres_diagnostics import CheckWriteLocksResult, WriteLockInfo

logger = logging.getLogger(__name__)

# Timeout for the entire tool operation (in seconds)
TOOL_TIMEOUT_SECONDS = 30


# SQL query to find pending write locks
# Filters for write-related lock modes that are NOT granted (i.e., waiting)
PENDING_WRITE_LOCKS_QUERY = """
SELECT 
    l.pid,
    c.relname AS table_name,
    l.mode AS lock_mode,
    l.granted,
    a.query,
    a.state
FROM pg_locks l
LEFT JOIN pg_class c ON l.relation = c.oid
LEFT JOIN pg_stat_activity a ON l.pid = a.pid
WHERE l.granted = false
  AND l.mode IN (
      'RowExclusiveLock',
      'ShareUpdateExclusiveLock', 
      'ShareRowExclusiveLock',
      'ExclusiveLock',
      'AccessExclusiveLock'
  )
ORDER BY l.pid;
"""


def _check_write_locks_sync() -> CheckWriteLocksResult:
    """
    Synchronous implementation of write locks check.
    Runs in a thread pool to avoid blocking the event loop.
    
    Steps:
    1. Connect to PostgreSQL
    2. Query pg_locks for pending write locks
    3. Return list of pending locks
    """
    conn = None
    try:
        # Step 1: Connect to PostgreSQL
        conn_params = settings.get_postgres_connection_params()
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Step 2: Execute query for pending write locks
        cursor.execute(PENDING_WRITE_LOCKS_QUERY)
        rows = cursor.fetchall()
        cursor.close()
        
        # Step 3: Build result
        locks: List[WriteLockInfo] = []
        for row in rows:
            locks.append(WriteLockInfo(
                pid=row[0],
                table_name=row[1],
                lock_mode=row[2],
                granted=row[3],
                query=row[4][:200] if row[4] else None,  # Truncate long queries
                state=row[5]
            ))
        
        return CheckWriteLocksResult(
            has_pending_locks=len(locks) > 0,
            pending_lock_count=len(locks),
            locks=locks if locks else None,
            error=None
        )
        
    except OperationalError as e:
        error_msg = str(e).strip()
        return CheckWriteLocksResult(
            has_pending_locks=False,
            pending_lock_count=0,
            locks=None,
            error=f"Database connection failed: {error_msg}"
        )
    except Exception as e:
        return CheckWriteLocksResult(
            has_pending_locks=False,
            pending_lock_count=0,
            locks=None,
            error=f"Query failed ({type(e).__name__}): {str(e)}"
        )
    finally:
        if conn:
            conn.close()


async def check_write_locks() -> CheckWriteLocksResult:
    """
    Check if the database has pending write locks.

    This tool queries pg_locks to find write operations that are waiting
    for locks. Pending write locks can indicate contention issues or
    potential deadlocks. Includes timeout handling.

    Write lock modes checked:
    - RowExclusiveLock (INSERT, UPDATE, DELETE)
    - ShareUpdateExclusiveLock (VACUUM, ANALYZE, CREATE INDEX CONCURRENTLY)
    - ShareRowExclusiveLock (CREATE TRIGGER)
    - ExclusiveLock (REFRESH MATERIALIZED VIEW CONCURRENTLY)
    - AccessExclusiveLock (DROP, ALTER, TRUNCATE)

    Returns:
        CheckWriteLocksResult with has_pending_locks=True if there are
        waiting write locks, along with details of each pending lock.
    """
    logger.info("Checking for pending write locks")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_check_write_locks_sync),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"Write locks check completed: pending_locks={result.pending_lock_count}")
        return result
    except asyncio.TimeoutError:
        logger.error(f"Write locks check timed out after {TOOL_TIMEOUT_SECONDS}s")
        return CheckWriteLocksResult(
            has_pending_locks=False,
            pending_lock_count=0,
            locks=None,
            error=f"Operation timed out after {TOOL_TIMEOUT_SECONDS} seconds"
        )


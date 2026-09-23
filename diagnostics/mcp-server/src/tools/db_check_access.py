"""Tool 1: db.checkAccess - Check if PostgreSQL database is reachable."""
import asyncio
import logging
from typing import Optional

import psycopg2
from psycopg2 import OperationalError

from ..config.settings import settings
from ..models.postgres_diagnostics import CheckAccessResult

logger = logging.getLogger(__name__)

# Timeout for the entire tool operation (in seconds)
TOOL_TIMEOUT_SECONDS = 30


def _check_access_sync(
    database_url: Optional[str] = None,
) -> CheckAccessResult:
    """
    Synchronous implementation of database accessibility check.
    Runs in a thread pool to avoid blocking the event loop.
    
    Steps:
    1. Parse database_url or use default settings
    2. Attempt to connect to PostgreSQL
    3. Execute simple SELECT 1 query
    4. Return success/failure result
    """
    conn = None
    try:
        # Use provided URL or default settings
        if database_url:
            # Parse connection string if provided
            conn = psycopg2.connect(database_url, connect_timeout=settings.postgres_timeout)
        else:
            # Use settings from environment/config
            conn_params = settings.get_postgres_connection_params()
            conn = psycopg2.connect(**conn_params)
        
        # Execute simple query to verify connection
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        
        return CheckAccessResult(
            db_accessible=True,
            error=None
        )
        
    except OperationalError as e:
        # Connection failed - database not reachable
        error_msg = str(e).strip()
        return CheckAccessResult(
            db_accessible=False,
            error=f"Database connection failed: {error_msg}"
        )
    except Exception as e:
        # Unexpected error
        return CheckAccessResult(
            db_accessible=False,
            error=f"Unexpected error ({type(e).__name__}): {str(e)}"
        )
    finally:
        if conn:
            conn.close()


async def check_access(
    database_url: Optional[str] = None,
) -> CheckAccessResult:
    """
    Check if PostgreSQL database is reachable.

    This async wrapper runs the blocking psycopg2 operations in a thread pool
    to avoid blocking the event loop. Includes timeout handling.

    Args:
        database_url: Optional connection string. If not provided, uses default settings.
                      Format: postgresql://user:password@host:port/database

    Returns:
        CheckAccessResult with db_accessible=True if connection successful,
        or db_accessible=False with error message if connection failed.
    """
    logger.info("Checking database access")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_check_access_sync, database_url),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"Database access check completed: accessible={result.db_accessible}")
        return result
    except asyncio.TimeoutError:
        logger.error(f"Database access check timed out after {TOOL_TIMEOUT_SECONDS}s")
        return CheckAccessResult(
            db_accessible=False,
            error=f"Operation timed out after {TOOL_TIMEOUT_SECONDS} seconds"
        )


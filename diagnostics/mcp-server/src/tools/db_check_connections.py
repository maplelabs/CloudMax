"""Tool 4: db.checkMaxConnections - Check current connections vs max allowed."""
import asyncio
import logging

import psycopg2
from psycopg2 import OperationalError

from ..config.settings import settings
from ..models.postgres_diagnostics import CheckMaxConnectionsResult

logger = logging.getLogger(__name__)

# Timeout for the entire tool operation (in seconds)
TOOL_TIMEOUT_SECONDS = 30


# SQL query to get max connections setting and current active connections
MAX_CONNECTIONS_QUERY = """
SELECT 
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_connections,
    (SELECT count(*) FROM pg_stat_activity) AS current_connections;
"""

# Threshold percentage to consider connections as "near saturation"
CONNECTION_SATURATION_THRESHOLD = 90.0  # 90%


def _check_max_connections_sync() -> CheckMaxConnectionsResult:
    """
    Synchronous implementation of max connections check.
    Runs in a thread pool to avoid blocking the event loop.
    
    Steps:
    1. Connect to PostgreSQL
    2. Query pg_settings for max_connections
    3. Query pg_stat_activity for current connection count
    4. Calculate usage percentage and determine if saturated
    """
    conn = None
    try:
        # Step 1: Connect to PostgreSQL
        conn_params = settings.get_postgres_connection_params()
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Step 2 & 3: Execute query
        cursor.execute(MAX_CONNECTIONS_QUERY)
        row = cursor.fetchone()
        cursor.close()
        
        if row is None:
            return CheckMaxConnectionsResult(
                connection_count=0,
                max_connection_limit=0,
                max_connections_reached=False,
                usage_percentage=0.0,
                error="Failed to retrieve connection statistics"
            )
        
        max_connections = row[0]
        current_connections = row[1]
        
        # Step 4: Calculate usage percentage
        usage_percentage = (current_connections / max_connections) * 100 if max_connections > 0 else 0.0
        
        # Determine if max connections reached or near saturation
        max_reached = (
            current_connections >= max_connections or 
            usage_percentage >= CONNECTION_SATURATION_THRESHOLD
        )
        
        return CheckMaxConnectionsResult(
            connection_count=current_connections,
            max_connection_limit=max_connections,
            max_connections_reached=max_reached,
            usage_percentage=round(usage_percentage, 2),
            error=None
        )
        
    except OperationalError as e:
        error_msg = str(e).strip()
        return CheckMaxConnectionsResult(
            connection_count=0,
            max_connection_limit=0,
            max_connections_reached=False,
            usage_percentage=0.0,
            error=f"Database connection failed: {error_msg}"
        )
    except Exception as e:
        return CheckMaxConnectionsResult(
            connection_count=0,
            max_connection_limit=0,
            max_connections_reached=False,
            usage_percentage=0.0,
            error=f"Query failed ({type(e).__name__}): {str(e)}"
        )
    finally:
        if conn:
            conn.close()


async def check_max_connections() -> CheckMaxConnectionsResult:
    """
    Check current active connections vs maximum allowed connections.

    This tool queries PostgreSQL system tables to determine:
    - Current number of active connections (pg_stat_activity)
    - Maximum allowed connections (pg_settings)
    - Whether the database is at or near connection saturation (>=90%)

    Includes timeout handling to prevent MCP server hanging.

    Returns:
        CheckMaxConnectionsResult with:
        - connection_count: Current active connections
        - max_connection_limit: Max allowed from pg_settings
        - max_connections_reached: True if at limit or >=90% usage
        - usage_percentage: Percentage of max connections in use
    """
    logger.info("Checking max connections")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_check_max_connections_sync),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"Max connections check completed: {result.connection_count}/{result.max_connection_limit}")
        return result
    except asyncio.TimeoutError:
        logger.error(f"Max connections check timed out after {TOOL_TIMEOUT_SECONDS}s")
        return CheckMaxConnectionsResult(
            connection_count=0,
            max_connection_limit=0,
            max_connections_reached=False,
            usage_percentage=0.0,
            error=f"Operation timed out after {TOOL_TIMEOUT_SECONDS} seconds"
        )


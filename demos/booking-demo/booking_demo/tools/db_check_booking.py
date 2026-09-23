"""Tool 2: db.checkBookingPresence - Check if a booking_id exists in a given table."""
import asyncio
import logging

import psycopg2
from psycopg2 import OperationalError, sql
from pydantic import BaseModel

from src.config.settings import settings
from booking_demo.config import ALLOWED_BOOKING_TABLES, is_booking_table_allowed


class CheckBookingPresenceResult(BaseModel):
    """Result of checking whether a booking exists in a table."""
    booking_exists: bool
    table_name: str
    booking_id: int
    error: str | None = None

logger = logging.getLogger(__name__)

# Timeout for the entire tool operation (in seconds)
TOOL_TIMEOUT_SECONDS = 30


def _check_booking_presence_sync(
    booking_id: int,
    table_name: str = "booking_info",
) -> CheckBookingPresenceResult:
    """
    Synchronous implementation of booking presence check.
    Runs in a thread pool to avoid blocking the event loop.
    
    Steps:
    1. Validate table_name against whitelist (SQL injection prevention)
    2. Connect to PostgreSQL
    3. Execute parameterized query to check if booking_id exists
    4. Return result
    """
    # Step 1: Validate table against whitelist
    if not is_booking_table_allowed(table_name):
        allowed = ", ".join(sorted(ALLOWED_BOOKING_TABLES))
        return CheckBookingPresenceResult(
            booking_exists=False,
            table_name=table_name,
            booking_id=booking_id,
            error=f"Table '{table_name}' is not in the allowed whitelist. Allowed tables: {allowed}"
        )
    
    conn = None
    try:
        # Step 2: Connect to PostgreSQL
        conn_params = settings.get_postgres_connection_params()
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Step 3: Execute parameterized query
        # Using psycopg2.sql module for safe table name injection
        # The booking_id is passed as a parameter (safe from SQL injection)
        query = sql.SQL("SELECT 1 FROM {} WHERE booking_id = %s LIMIT 1").format(
            sql.Identifier(table_name)
        )
        cursor.execute(query, (booking_id,))
        result = cursor.fetchone()
        cursor.close()
        
        # Step 4: Return result
        return CheckBookingPresenceResult(
            booking_exists=result is not None, 
            table_name=table_name,
            booking_id=booking_id,
            error=None
        )
        
    except OperationalError as e:
        error_msg = str(e).strip()
        return CheckBookingPresenceResult(
            booking_exists=False,
            table_name=table_name,
            booking_id=booking_id,
            error=f"Database connection failed: {error_msg}"
        )
    except Exception as e:
        return CheckBookingPresenceResult(
            booking_exists=False,
            table_name=table_name,
            booking_id=booking_id,
            error=f"Query failed ({type(e).__name__}): {str(e)}"
        )
    finally:
        if conn:
            conn.close()


async def check_booking_presence(
    booking_id: int,
    table_name: str = "booking_info",
) -> CheckBookingPresenceResult:
    """
    Check if a booking_id exists in the specified table.

    This tool validates the table name against a whitelist before querying
    to prevent SQL injection attacks. Includes timeout handling.

    Args:
        booking_id: The booking ID to search for (BIGINT)
        table_name: Table to search in. Must be in whitelist.
                    Default: "booking_info"
                    Allowed: booking_info, booking_details, booked_rooms

    Returns:
        CheckBookingPresenceResult with booking_exists=True if found,
        or booking_exists=False with optional error message.
    """
    logger.info(f"Checking booking presence: booking_id={booking_id}, table={table_name}")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_check_booking_presence_sync, booking_id, table_name),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"Booking presence check completed: exists={result.booking_exists}")
        return result
    except asyncio.TimeoutError:
        logger.error(f"Booking presence check timed out after {TOOL_TIMEOUT_SECONDS}s")
        return CheckBookingPresenceResult(
            booking_exists=False,
            table_name=table_name,
            booking_id=booking_id,
            error=f"Operation timed out after {TOOL_TIMEOUT_SECONDS} seconds"
        )


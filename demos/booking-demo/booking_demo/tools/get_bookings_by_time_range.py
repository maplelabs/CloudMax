"""Get all booking IDs created within a time range."""
import asyncio
import logging
from datetime import datetime

import psycopg2
from psycopg2 import OperationalError, sql

from src.config.settings import settings
from booking_demo.config import ALLOWED_BOOKING_TABLES, is_booking_table_allowed
from booking_demo.models.bookings_by_time_range import BookingsByTimeRangeResult

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_SECONDS = 30


def _get_bookings_by_time_range_sync(
    start_time: datetime,
    end_time: datetime,
    table_name: str = "booking_info",
) -> BookingsByTimeRangeResult:
    """Query database for booking IDs created within time range."""
    
    # Validate table against whitelist
    if not is_booking_table_allowed(table_name):
        allowed = ", ".join(sorted(ALLOWED_BOOKING_TABLES))
        return BookingsByTimeRangeResult(
            booking_ids=[],
            count=0,
            table_name=table_name,
            start_time=start_time,
            end_time=end_time,
            error=f"Table '{table_name}' not in whitelist. Allowed: {allowed}"
        )
    
    conn = None
    try:
        # Connect to PostgreSQL
        conn_params = settings.get_postgres_connection_params()
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Query for booking IDs in time range
        query = sql.SQL(
            "SELECT booking_id FROM {} WHERE created_at BETWEEN %s AND %s ORDER BY created_at"
        ).format(sql.Identifier(table_name))
        
        cursor.execute(query, (start_time, end_time))
        results = cursor.fetchall()
        cursor.close()
        
        # Extract booking IDs from results
        booking_ids = [row[0] for row in results]
        
        logger.info(
            f"Found {len(booking_ids)} bookings in {table_name} "
            f"between {start_time.isoformat()} and {end_time.isoformat()}"
        )
        
        return BookingsByTimeRangeResult(
            booking_ids=booking_ids,
            count=len(booking_ids),
            table_name=table_name,
            start_time=start_time,
            end_time=end_time,
            error=None
        )
        
    except OperationalError as e:
        return BookingsByTimeRangeResult(
            booking_ids=[],
            count=0,
            table_name=table_name,
            start_time=start_time,
            end_time=end_time,
            error=f"Database connection failed: {str(e).strip()}"
        )
    except Exception as e:
        return BookingsByTimeRangeResult(
            booking_ids=[],
            count=0,
            table_name=table_name,
            start_time=start_time,
            end_time=end_time,
            error=f"Query failed ({type(e).__name__}): {str(e)}"
        )
    finally:
        if conn:
            conn.close()


async def get_bookings_by_time_range(
    start_time: datetime,
    end_time: datetime,
    table_name: str = "booking_info",
) -> BookingsByTimeRangeResult:
    """Get all booking IDs created within a time range.
    
    Args:
        start_time: Start of time range (inclusive)
        end_time: End of time range (inclusive)
        table_name: Table to query (default: booking_info)
    
    Returns:
        BookingsByTimeRangeResult with list of booking IDs and count
    """
    logger.info(
        f"Getting bookings by time range: {start_time.isoformat()} to {end_time.isoformat()}"
    )
    
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _get_bookings_by_time_range_sync,
                start_time,
                end_time,
                table_name
            ),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"Found {result.count} bookings in time range")
        return result
    except asyncio.TimeoutError:
        logger.error(f"Query timed out after {TOOL_TIMEOUT_SECONDS}s")
        return BookingsByTimeRangeResult(
            booking_ids=[],
            count=0,
            table_name=table_name,
            start_time=start_time,
            end_time=end_time,
            error=f"Operation timed out after {TOOL_TIMEOUT_SECONDS} seconds"
        )


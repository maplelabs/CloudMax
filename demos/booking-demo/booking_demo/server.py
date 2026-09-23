"""MCP server extension for the booking-specific diagnostic demo.

Run this module instead of ``src.main`` to expose the demo tools alongside
all generic core diagnostics.
"""
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_ROOT = REPO_ROOT / "integrations" / "diagnostic-mcp-server"
DEMO_ROOT = REPO_ROOT / "examples" / "booking-demo"
sys.path.insert(0, str(SERVER_ROOT))
sys.path.insert(0, str(DEMO_ROOT))

from booking_demo.models.booking_dlq import BookingDLQResult
from booking_demo.models.booking_processed import BookingProcessedResult
from booking_demo.models.bookings_by_time_range import BookingsByTimeRangeResult
from booking_demo.tools.check_booking_dlq import check_booking_dlq
from booking_demo.tools.check_booking_processed import check_booking_processed
from booking_demo.tools.db_check_booking import (
    CheckBookingPresenceResult,
    check_booking_presence,
)
from booking_demo.tools.get_bookings_by_time_range import get_bookings_by_time_range
from src.main import main as start_core_server
from src.main import mcp


@mcp.tool()
async def db_check_booking_presence_tool(
    booking_id: int,
    table_name: str = "booking_info",
) -> CheckBookingPresenceResult:
    """Check if a booking ID exists in an allowed booking table."""
    return await check_booking_presence(booking_id, table_name)


@mcp.tool()
async def get_bookings_by_time_range_tool(
    start_time: str,
    end_time: str,
    table_name: str = "booking_info",
) -> BookingsByTimeRangeResult:
    """Get booking IDs created within an ISO-formatted time range."""
    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    return await get_bookings_by_time_range(start_dt, end_dt, table_name)


@mcp.tool()
async def check_booking_processed_tool(
    booking_id: int,
    consumer_group: str,
    topic: str,
    time_buffer_minutes: int,
) -> BookingProcessedResult:
    """Trace a booking through its database, Kafka, and consumer stages."""
    return await check_booking_processed(
        booking_id, consumer_group, topic, time_buffer_minutes
    )


@mcp.tool()
async def check_booking_dlq_tool(
    booking_id: int,
    dlq_topic: str,
    alert_created_at: str,
    time_window_minutes: int = 10,
) -> BookingDLQResult:
    """Check whether a booking appears in a DLQ near an alert timestamp."""
    alert_time = datetime.fromisoformat(alert_created_at.replace("Z", "+00:00"))
    if alert_time.tzinfo is None:
        alert_time = alert_time.replace(tzinfo=timezone.utc)
    return await check_booking_dlq(
        booking_id, dlq_topic, alert_time, time_window_minutes
    )


def main() -> None:
    """Start the generic MCP server with booking-demo tools registered."""
    print("Starting Diagnostic MCP Server with the booking-demo extension.")
    start_core_server()


if __name__ == "__main__":
    main()

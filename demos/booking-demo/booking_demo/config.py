"""Booking-demo-only configuration."""

ALLOWED_BOOKING_TABLES = frozenset({
    "booking_info",
    "booking_details",
    "booked_rooms",
})


def is_booking_table_allowed(table_name: str) -> bool:
    """Return whether a table belongs to the demo's explicit allowlist."""
    return table_name in ALLOWED_BOOKING_TABLES

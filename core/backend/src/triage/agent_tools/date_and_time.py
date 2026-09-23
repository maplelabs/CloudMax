import re
from datetime import datetime, timezone, timedelta

from langchain.tools import tool


@tool
def parse_relative_time(time_expression: str) -> str:
    """
    Convert relative time expressions to UTC timestamps.
    Supports expressions like:
    - "now" - current time
    - "now-1m" - 1 minute ago
    - "now-5s" - 5 seconds ago
    - "now-2h" - 2 hours ago
    - "now-3d" - 3 days ago
    - "now-1w" - 1 week ago
    Supported time units: s (seconds), m (minutes), h (hours), d (days), w (weeks)
    Note: Only integer values are allowed (e.g., "now-5m" not "now-5.5m")

    Args:
        time_expression: Relative time expression (e.g., "now", "now-1m", "now-2h")

    Returns:
        UTC timestamp in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
    """
    now = datetime.now(timezone.utc)

    # Handle "now" case
    if time_expression.strip().lower() == "now":
        return now.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Parse relative time expressions like "now-1m", "now-2h", etc.
    pattern = r'^now-(\d+[smhdw])$'
    match = re.match(pattern, time_expression.strip().lower())

    if not match:
        raise ValueError(f"Invalid time expression: {time_expression}. "
                         f"Supported formats: 'now', 'now-1m', 'now-2h', etc.")

    time_part = match.group(1)
    unit = time_part[-1]  # Last character is the unit
    amount = int(time_part[:-1])  # Everything except last character is the amount

    # Convert to timedelta based on unit
    if unit == 's':  # seconds
        delta = timedelta(seconds=amount)
    elif unit == 'm':  # minutes
        delta = timedelta(minutes=amount)
    elif unit == 'h':  # hours
        delta = timedelta(hours=amount)
    elif unit == 'd':  # days
        delta = timedelta(days=amount)
    elif unit == 'w':  # weeks
        delta = timedelta(weeks=amount)
    else:
        raise ValueError(f"Unsupported time unit: {unit}")

    # Subtract the delta from now (since it's "ago")
    target_time = now - delta
    return target_time.strftime('%Y-%m-%dT%H:%M:%SZ')

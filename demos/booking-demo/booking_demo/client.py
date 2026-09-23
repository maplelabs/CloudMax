#!/usr/bin/env python3
"""Direct Kafka client for the booking diagnostics demo.

Usage:
    python ../../demos/booking-demo/booking_demo/client.py check-processed --booking-id 6
    python ../../demos/booking-demo/booking_demo/client.py check-dlq --booking-id 6
    python ../../demos/booking-demo/booking_demo/client.py all --booking-id 6
"""
import argparse
import asyncio
import sys

# Make both the core server package and this example package importable.
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_ROOT = REPO_ROOT / "integrations" / "diagnostic-mcp-server"
DEMO_ROOT = REPO_ROOT / "examples" / "booking-demo"
sys.path.insert(0, str(SERVER_ROOT))
sys.path.insert(0, str(DEMO_ROOT))

from booking_demo.tools.check_booking_processed import check_booking_processed
from booking_demo.tools.check_booking_dlq import check_booking_dlq


def print_result(title: str, data: dict):
    """Pretty print a result."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)
    for key, value in data.items():
        if value is not None:
            print(f"  {key}: {value}")


async def cmd_check_processed(booking_id: int, consumer_group: str, topic: str):
    """Check if booking was processed."""
    result = await check_booking_processed(
        booking_id=booking_id,
        consumer_group=consumer_group,
        topic=topic
    )
    
    print_result(f"BOOKING PROCESSED CHECK (ID: {booking_id})", {
        "status": result.status.value,
        "created_at": result.created_at,
        "message_offset": result.message_offset,
        "consumer_offset": result.consumer_offset,
        "lag": result.lag,
        "in_booking_details": result.in_booking_details,
        "messages_scanned": result.messages_scanned,
        "message": result.message,
        "error": result.error,
    })
    
    # Status summary
    status_icons = {
        "PROCESSED": "✅",
        "PENDING": "⏳",
        "CONSUMED_BUT_NOT_PROCESSED": "⚠️",
        "PRODUCER_EXCEPTION": "❌",
        "BOOKING_NOT_FOUND": "❓",
    }
    icon = status_icons.get(result.status.value, "")
    print(f"\n  {icon} {result.status.value}")
    
    return result


async def cmd_check_dlq(booking_id: int, topic: str):
    """Check if booking is in DLQ."""
    from datetime import datetime, timezone

    # Use current time as alert_created_at since this is a test client
    alert_time = datetime.now(timezone.utc)
    dlq_topic = f"{topic}-dlq"  # Derive DLQ topic from main topic

    result = await check_booking_dlq(
        booking_id=booking_id,
        dlq_topic=dlq_topic,
        alert_created_at=alert_time,
        time_window_minutes=10
    )
    
    print_result(f"DLQ CHECK (ID: {booking_id})", {
        "status": result.status.value,
        "topic": result.topic,
        "message": result.message,
        "error": result.error,
    })
    
    icon = "✅ FOUND IN DLQ" if result.status.value == "FOUND" else "❌ NOT IN DLQ"
    print(f"\n  {icon}")
    
    return result


async def cmd_all(booking_id: int, consumer_group: str, topic: str):
    """Run all checks."""
    print("\n" + "="*60)
    print(" RUNNING ALL KAFKA BOOKING CHECKS")
    print("="*60)
    
    await cmd_check_processed(booking_id, consumer_group, topic)
    await cmd_check_dlq(booking_id, topic)
    
    print("\n" + "="*60)
    print(" ALL CHECKS COMPLETED")
    print("="*60 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Kafka Booking Diagnostic Client")
    parser.add_argument('command', choices=['check-processed', 'check-dlq', 'all'])
    parser.add_argument('--booking-id', type=int, required=True, help='Booking ID to check')
    parser.add_argument('--consumer-group', default='booking-post-processing-group')
    parser.add_argument('--topic', default='booking-events')
    
    args = parser.parse_args()
    
    print("="*60)
    print(" Kafka Booking Diagnostic Client")
    print("="*60)
    print(f"  Booking ID: {args.booking_id}")
    print(f"  Topic: {args.topic}")
    
    if args.command == 'check-processed':
        await cmd_check_processed(args.booking_id, args.consumer_group, args.topic)
    elif args.command == 'check-dlq':
        await cmd_check_dlq(args.booking_id, args.topic)
    elif args.command == 'all':
        await cmd_all(args.booking_id, args.consumer_group, args.topic)


if __name__ == "__main__":
    asyncio.run(main())


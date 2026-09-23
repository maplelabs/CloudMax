"""Check if a booking exists in the DLQ (simple boolean check)."""
import asyncio
import json
import logging
from datetime import datetime, timedelta

from confluent_kafka import Consumer, KafkaException, TopicPartition

from src.config.settings import settings

from booking_demo.models.booking_dlq import BookingDLQResult, BookingDLQStatus

logger = logging.getLogger(__name__)

TOOL_TIMEOUT_SECONDS = 30
DEFAULT_TIME_WINDOW_MINUTES = 10


def _search_booking_in_dlq_sync(
    booking_id: int,
    dlq_topic: str,
    alert_created_at: datetime,
    time_window_minutes: int = DEFAULT_TIME_WINDOW_MINUTES,
) -> BookingDLQResult:
    """Check if booking_id exists in DLQ within time window. Returns as soon as found."""
    consumer = None

    try:
        # Create Kafka consumer
        consumer_config = settings.get_kafka_config()
        consumer_config.update({
            "group.id": f"check-booking-dlq-{booking_id}-{datetime.now().timestamp()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        consumer = Consumer(consumer_config)

        # Verify topic exists
        metadata = consumer.list_topics(dlq_topic, timeout=10)
        if dlq_topic not in metadata.topics:
            return BookingDLQResult(
                booking_id=booking_id,
                status=BookingDLQStatus.NOT_FOUND,
                topic=dlq_topic,
                message=f"DLQ topic '{dlq_topic}' does not exist"
            )

        # Get partitions
        partitions = metadata.topics[dlq_topic].partitions
        if not partitions:
            return BookingDLQResult(
                booking_id=booking_id,
                status=BookingDLQStatus.NOT_FOUND,
                topic=dlq_topic,
                message=f"No partitions in topic '{dlq_topic}'"
            )

        # Calculate time window
        start_time = alert_created_at - timedelta(minutes=time_window_minutes)
        end_time = alert_created_at + timedelta(minutes=time_window_minutes)

        logger.info(
            f"Checking DLQ '{dlq_topic}' for booking {booking_id} "
            f"between {start_time.isoformat()} and {end_time.isoformat()}"
        )

        # Search each partition
        for partition_id in partitions.keys():
            tp = TopicPartition(dlq_topic, partition_id)

            # Get offset range for time window
            start_ts_ms = int(start_time.timestamp() * 1000)
            end_ts_ms = int(end_time.timestamp() * 1000)

            start_offsets = consumer.offsets_for_times(
                [TopicPartition(dlq_topic, partition_id, start_ts_ms)]
            )

            if not start_offsets or start_offsets[0].offset < 0:
                continue

            start_offset = start_offsets[0].offset

            end_offsets = consumer.offsets_for_times(
                [TopicPartition(dlq_topic, partition_id, end_ts_ms)]
            )

            if end_offsets and end_offsets[0].offset >= 0:
                end_offset = end_offsets[0].offset
            else:
                low, high = consumer.get_watermark_offsets(tp, timeout=10)
                end_offset = high

            if start_offset >= end_offset:
                continue

            # Seek and scan messages
            consumer.assign([TopicPartition(dlq_topic, partition_id, start_offset)])

            while True:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    break
                if msg.error():
                    continue

                if msg.offset() >= end_offset:
                    break

                # Check if this message contains the booking_id
                try:
                    value = msg.value()
                    if value:
                        data = json.loads(value.decode('utf-8'))
                        original = data.get('original_message', data)

                        msg_booking_id = (
                            original.get('booking_id') or
                            original.get('bookingId') or
                            original.get('id')
                        )

                        # FOUND! Return immediately
                        if msg_booking_id and int(msg_booking_id) == booking_id:
                            return BookingDLQResult(
                                booking_id=booking_id,
                                status=BookingDLQStatus.FOUND,
                                topic=dlq_topic,
                                message=f"Booking {booking_id} found in DLQ"
                            )

                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

        # Not found after scanning all partitions
        return BookingDLQResult(
            booking_id=booking_id,
            status=BookingDLQStatus.NOT_FOUND,
            topic=dlq_topic,
            message=f"Booking {booking_id} not found in DLQ"
        )

    except KafkaException as e:
        return BookingDLQResult(
            booking_id=booking_id,
            status=BookingDLQStatus.ERROR,
            topic=dlq_topic,
            message=f"Kafka error: {str(e)}",
            error=str(e)
        )
    except Exception as e:
        return BookingDLQResult(
            booking_id=booking_id,
            status=BookingDLQStatus.ERROR,
            topic=dlq_topic,
            message=f"Error: {str(e)}",
            error=str(e)
        )
    finally:
        if consumer:
            consumer.close()


async def check_booking_dlq(
    booking_id: int,
    dlq_topic: str,
    alert_created_at: datetime,
    time_window_minutes: int = DEFAULT_TIME_WINDOW_MINUTES,
) -> BookingDLQResult:
    """Check if booking exists in DLQ within time window around alert creation."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _search_booking_in_dlq_sync,
                booking_id,
                dlq_topic,
                alert_created_at,
                time_window_minutes
            ),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"DLQ check: booking {booking_id} - {result.status}")
        return result
    except asyncio.TimeoutError:
        return BookingDLQResult(
            booking_id=booking_id,
            status=BookingDLQStatus.ERROR,
            topic=dlq_topic,
            message=f"Timeout after {TOOL_TIMEOUT_SECONDS}s",
            error=f"Operation timed out"
        )


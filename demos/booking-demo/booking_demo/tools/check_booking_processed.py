"""Tool: check_booking_processed - Check if a booking has been processed by the consumer."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import psycopg2
from psycopg2 import OperationalError
from confluent_kafka import Consumer, KafkaException, TopicPartition
from confluent_kafka.admin import AdminClient

from src.config.settings import settings

from booking_demo.models.booking_processed import BookingProcessedResult, BookingProcessedStatus

logger = logging.getLogger(__name__)

# Timeout for the entire tool operation (in seconds)
TOOL_TIMEOUT_SECONDS = 30
# Default time buffer for searching Kafka messages (minutes)
DEFAULT_TIME_BUFFER_MINUTES = 5


def _create_error_result(
    booking_id: int,
    error_message: str,
    status: BookingProcessedStatus = BookingProcessedStatus.BOOKING_NOT_FOUND,
) -> BookingProcessedResult:
    """Helper to create error result."""
    return BookingProcessedResult(
        booking_id=booking_id,
        status=status,
        error=error_message,
    )


def _get_booking_created_at(booking_id: int) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Step 1: Query booking_info table for created_at timestamp.
    Returns (created_at, error_message).
    """
    conn = None
    try:
        conn_params = settings.get_postgres_connection_params()
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT created_at FROM booking_info WHERE booking_id = %s",
            (booking_id,)
        )
        result = cursor.fetchone()
        cursor.close()
        
        if result is None:
            return None, f"Booking ID {booking_id} not found in booking_info table"
        
        created_at = result[0]
        # Ensure timezone-aware datetime
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, None
        
    except OperationalError as e:
        return None, f"Database connection failed: {str(e).strip()}"
    except Exception as e:
        return None, f"Database query failed ({type(e).__name__}): {str(e)}"
    finally:
        if conn:
            conn.close()


def _check_booking_in_details(booking_id: int) -> Tuple[bool, Optional[str]]:
    """
    Step 6: Check if booking exists in booking_details table.
    Returns (exists, error_message).
    """
    conn = None
    try:
        conn_params = settings.get_postgres_connection_params()
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT 1 FROM booking_details WHERE booking_id = %s LIMIT 1",
            (booking_id,)
        )
        result = cursor.fetchone()
        cursor.close()
        
        return result is not None, None
        
    except Exception as e:
        return False, f"Failed to check booking_details: {str(e)}"
    finally:
        if conn:
            conn.close()


def _search_booking_in_kafka(
    booking_id: int,
    topic: str,
    start_time: datetime,
    end_time: datetime,
) -> Tuple[Optional[int], int, Optional[str]]:
    """
    Steps 3-4: Search for booking_id in Kafka messages within time range.
    Returns (message_offset, messages_scanned, error_message).
    """
    consumer = None
    try:
        # Create a temporary consumer with unique group ID
        consumer_config = settings.get_kafka_config()
        consumer_config.update({
            "group.id": f"check-booking-processed-{booking_id}-{datetime.now().timestamp()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        consumer = Consumer(consumer_config)
        
        # Get partition info for topic
        metadata = consumer.list_topics(topic, timeout=10)
        if topic not in metadata.topics:
            return None, 0, f"Topic '{topic}' not found"
        
        partitions = metadata.topics[topic].partitions
        if not partitions:
            return None, 0, f"No partitions found for topic '{topic}'"
        
        messages_scanned = 0
        found_offset = None
        
        # Search each partition
        for partition_id in partitions.keys():
            tp = TopicPartition(topic, partition_id)
            
            # Get offset for start_time
            start_ts_ms = int(start_time.timestamp() * 1000)
            end_ts_ms = int(end_time.timestamp() * 1000)
            
            # Get offset for start time
            start_offsets = consumer.offsets_for_times([TopicPartition(topic, partition_id, start_ts_ms)])
            if not start_offsets or start_offsets[0].offset < 0:
                continue  # No messages at this time
            
            start_offset = start_offsets[0].offset
            
            # Get offset for end time (or use latest if beyond)
            end_offsets = consumer.offsets_for_times([TopicPartition(topic, partition_id, end_ts_ms)])
            if end_offsets and end_offsets[0].offset >= 0:
                end_offset = end_offsets[0].offset
            else:
                # End time is beyond latest message, get latest offset
                low, high = consumer.get_watermark_offsets(tp, timeout=10)
                end_offset = high
            
            # Seek to start offset and consume until end offset
            consumer.assign([TopicPartition(topic, partition_id, start_offset)])

            while True:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    break
                if msg.error():
                    continue

                current_offset = msg.offset()
                if current_offset >= end_offset:
                    break

                messages_scanned += 1

                # Parse message and check for booking_id
                try:
                    value = msg.value()
                    if value:
                        data = json.loads(value.decode('utf-8'))
                        # Check various possible field names for booking_id
                        msg_booking_id = (
                            data.get('booking_id') or
                            data.get('bookingId') or
                            data.get('id')
                        )
                        if msg_booking_id and int(msg_booking_id) == booking_id:
                            found_offset = current_offset
                            break
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

            if found_offset is not None:
                break

        return found_offset, messages_scanned, None

    except KafkaException as e:
        return None, 0, f"Kafka error: {str(e)}"
    except Exception as e:
        return None, 0, f"Error searching Kafka ({type(e).__name__}): {str(e)}"
    finally:
        if consumer:
            consumer.close()


def _get_consumer_committed_offset(
    consumer_group: str,
    topic: str,
    partition: int = 0,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Step 5: Get the committed offset for a consumer group.
    Returns (committed_offset, error_message).
    """
    try:
        admin_config = settings.get_kafka_config()
        admin_client = AdminClient(admin_config)

        from confluent_kafka import ConsumerGroupTopicPartitions

        group_req = [ConsumerGroupTopicPartitions(consumer_group)]
        futures = admin_client.list_consumer_group_offsets(group_req)

        group_result = futures[consumer_group].result()
        committed_tps = group_result.topic_partitions or []

        for tp in committed_tps:
            if tp.topic == topic and tp.partition == partition:
                return tp.offset, None

        return None, f"No committed offset found for {consumer_group} on {topic}[{partition}]"

    except KafkaException as e:
        return None, f"Kafka error getting committed offset: {str(e)}"
    except Exception as e:
        return None, f"Error getting committed offset ({type(e).__name__}): {str(e)}"


def _check_booking_processed_sync(
    booking_id: int,
    consumer_group: str,
    topic: str,
    time_buffer_minutes: int,
) -> BookingProcessedResult:
    """
    Synchronous implementation of check_booking_processed.
    """
    # Step 1: Get created_at from booking_info
    created_at, error = _get_booking_created_at(booking_id)
    if error:
        return _create_error_result(
            booking_id,
            error,
            BookingProcessedStatus.BOOKING_NOT_FOUND
        )

    # Step 2: Create time range
    start_time = created_at - timedelta(minutes=time_buffer_minutes)
    end_time = created_at + timedelta(minutes=time_buffer_minutes)

    # Steps 3-4: Search for booking in Kafka
    message_offset, messages_scanned, error = _search_booking_in_kafka(
        booking_id, topic, start_time, end_time
    )

    if error:
        return BookingProcessedResult(
            booking_id=booking_id,
            status=BookingProcessedStatus.PRODUCER_EXCEPTION,
            created_at=created_at,
            topic=topic,
            consumer_group=consumer_group,
            search_range_start=start_time,
            search_range_end=end_time,
            messages_scanned=messages_scanned,
            error=error,
            message="Error while searching Kafka topic"
        )

    if message_offset is None:
        # Booking not found in Kafka - producer exception
        return BookingProcessedResult(
            booking_id=booking_id,
            status=BookingProcessedStatus.PRODUCER_EXCEPTION,
            created_at=created_at,
            topic=topic,
            consumer_group=consumer_group,
            search_range_start=start_time,
            search_range_end=end_time,
            messages_scanned=messages_scanned,
            message=f"Booking exists in DB but was never published to Kafka topic '{topic}'. "
                    f"Scanned {messages_scanned} messages in time range."
        )

    # Step 5: Get consumer committed offset
    consumer_offset, error = _get_consumer_committed_offset(consumer_group, topic)

    if error:
        return BookingProcessedResult(
            booking_id=booking_id,
            status=BookingProcessedStatus.PENDING,
            created_at=created_at,
            message_offset=message_offset,
            topic=topic,
            consumer_group=consumer_group,
            search_range_start=start_time,
            search_range_end=end_time,
            messages_scanned=messages_scanned,
            error=error,
            message="Found booking in Kafka but could not verify consumer offset"
        )

    # Step 6: Compare offsets
    if message_offset < consumer_offset:
        # Message was consumed, check booking_details
        in_details, error = _check_booking_in_details(booking_id)

        if in_details:
            return BookingProcessedResult(
                booking_id=booking_id,
                status=BookingProcessedStatus.PROCESSED,
                created_at=created_at,
                message_offset=message_offset,
                consumer_offset=consumer_offset,
                in_booking_details=True,
                topic=topic,
                consumer_group=consumer_group,
                search_range_start=start_time,
                search_range_end=end_time,
                messages_scanned=messages_scanned,
                message="Booking was consumed and processed successfully"
            )
        else:
            return BookingProcessedResult(
                booking_id=booking_id,
                status=BookingProcessedStatus.CONSUMED_BUT_NOT_PROCESSED,
                created_at=created_at,
                message_offset=message_offset,
                consumer_offset=consumer_offset,
                in_booking_details=False,
                topic=topic,
                consumer_group=consumer_group,
                search_range_start=start_time,
                search_range_end=end_time,
                messages_scanned=messages_scanned,
                message="Consumer read the message but booking not found in booking_details. "
                        "Check DLQ or service logs for processing errors.",
                error=error
            )
    else:
        # Consumer hasn't reached this message yet - PENDING
        lag = message_offset - consumer_offset + 1
        return BookingProcessedResult(
            booking_id=booking_id,
            status=BookingProcessedStatus.PENDING,
            created_at=created_at,
            message_offset=message_offset,
            consumer_offset=consumer_offset,
            lag=lag,
            topic=topic,
            consumer_group=consumer_group,
            search_range_start=start_time,
            search_range_end=end_time,
            messages_scanned=messages_scanned,
            message=f"Consumer lag: message at offset {message_offset}, "
                    f"consumer at offset {consumer_offset} ({lag} messages behind)"
        )


async def check_booking_processed(
    booking_id: int,
    consumer_group: str = "booking-post-processing-group",
    topic: str = "booking-events",
    time_buffer_minutes: int = DEFAULT_TIME_BUFFER_MINUTES,
) -> BookingProcessedResult:
    """
    Check if a booking has been processed by the Kafka consumer.

    This tool performs a multi-step diagnostic:
    1. Checks if booking exists in booking_info table (gets created_at)
    2. Searches Kafka topic for the booking message within a time window
    3. Compares message offset with consumer group's committed offset
    4. If consumed, verifies booking exists in booking_details table

    Args:
        booking_id: The booking ID to check
        consumer_group: Kafka consumer group to check offset for
                       Default: "booking-post-processing-group"
        topic: Kafka topic to search for the booking message
               Default: "booking-events"
        time_buffer_minutes: Minutes before/after created_at to search
                            Default: 5 (searches ±5 minutes)

    Returns:
        BookingProcessedResult with status:
        - PROCESSED: Consumer consumed + stored in booking_details
        - PENDING: Message in Kafka but consumer hasn't reached it (lag)
        - CONSUMED_BUT_NOT_PROCESSED: Consumed but not in DB (check DLQ)
        - PRODUCER_EXCEPTION: Booking created but never published to Kafka
        - BOOKING_NOT_FOUND: Booking ID doesn't exist in booking_info
    """
    logger.info(
        f"Checking booking processed: booking_id={booking_id}, "
        f"consumer_group={consumer_group}, topic={topic}"
    )

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _check_booking_processed_sync,
                booking_id,
                consumer_group,
                topic,
                time_buffer_minutes,
            ),
            timeout=TOOL_TIMEOUT_SECONDS
        )
        logger.info(f"Booking processed check completed: status={result.status}")
        return result
    except asyncio.TimeoutError:
        logger.error(f"Booking processed check timed out after {TOOL_TIMEOUT_SECONDS}s")
        return BookingProcessedResult(
            booking_id=booking_id,
            status=BookingProcessedStatus.BOOKING_NOT_FOUND,
            error=f"Operation timed out after {TOOL_TIMEOUT_SECONDS} seconds"
        )

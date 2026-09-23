"""Get consumer lag tool - Check consumer group lag per partition."""
import asyncio
from typing import Optional, Dict, Tuple

from confluent_kafka import (
    KafkaException,
    TopicPartition,
    ConsumerGroupTopicPartitions,
)
from confluent_kafka.admin import AdminClient, OffsetSpec

from ..config.settings import settings
from ..models.consumer_lag import ConsumerLagResult, PartitionLag


def _create_error_result(
    consumer_group: str,
    topic: Optional[str],
    error_message: str,
) -> ConsumerLagResult:
    """Helper to create error result."""
    return ConsumerLagResult(
        consumer_group=consumer_group,
        topic=topic,
        total_lag=None,
        partition_count=None,
        partitions=None,
        error=error_message,
    )

def _fetch_consumer_lag_sync(
    consumer_group: str,
    topic: Optional[str],
) -> ConsumerLagResult:
    """
    Synchronous implementation of consumer lag fetching.
    This runs in a thread pool to avoid blocking the event loop.
    """
    bootstrap_servers = settings.kafka_bootstrap_servers

    try:
        admin_config = settings.get_kafka_config()
        admin_client = AdminClient(admin_config)

        # 1) Get committed offsets for this consumer group

        try:
            # Ask broker: "give me all committed offsets for this group"
            group_req = [ConsumerGroupTopicPartitions(consumer_group)]
            futures = admin_client.list_consumer_group_offsets(group_req)
            #offset is an unique identifier for the message. 
            group_result = futures[consumer_group].result()
            committed_tps = group_result.topic_partitions or [] #Extract committed offsets per (topic, partition).
        except KafkaException as e:
            # If the group does not exist or broker not reachable, we land here
            err_msg = str(e)
            return _create_error_result(
                consumer_group,
                topic,
                f"Kafka error while fetching committed offsets for group "
                f"'{consumer_group}': {err_msg}",
            )
        except KeyError:
            # Shouldn't usually happen, but be safe
            return _create_error_result(
                consumer_group,
                topic,
                f"Consumer group '{consumer_group}' not found in Kafka cluster.",
            )

        if topic:
            committed_tps = [tp for tp in committed_tps if tp.topic == topic]

        if not committed_tps:
            # Could be: group has no offsets yet, wrong topic, or very old broker
            msg = (
                f"No committed offsets found for consumer group '{consumer_group}'"
                + (f" on topic '{topic}'." if topic else ".")
                + " The group may not have processed any messages yet, "
                  "or the Kafka version may not support listing offsets this way."
            )
            return _create_error_result(consumer_group, topic, msg)

        # 2) Get latest offsets for these partitions(end of log)

        latest_req = {
            TopicPartition(tp.topic, tp.partition): OffsetSpec.latest()
            for tp in committed_tps
        }

        latest_futures = admin_client.list_offsets(latest_req)

        latest_offsets: Dict[Tuple[str, int], int] = {}
        for tp, fut in latest_futures.items():
            try:
                info = fut.result()
                latest_offsets[(tp.topic, tp.partition)] = info.offset
            except KafkaException:
                # Skip partitions where end offset lookup failed
                continue

        if not latest_offsets:
            return _create_error_result(
                consumer_group,
                topic,
                "Failed to fetch latest offsets for partitions. "
                "Check broker health and ACLs.",
            )

        # 3) Compute lag per partition

        partition_lags = []
        total_lag = 0

        for tp in committed_tps:
            key = (tp.topic, tp.partition)
            log_end_offset = latest_offsets.get(key)

            if log_end_offset is None:
                # Could not get end offset for this partition
                continue

            current_offset = tp.offset
            if current_offset >= 0:
                lag = max(log_end_offset - current_offset, 0)
            else:
                # No committed offset: full backlog
                lag = log_end_offset
                current_offset = 0

            total_lag += lag

            partition_lags.append(
                PartitionLag(
                    topic=tp.topic,
                    partition=tp.partition,
                    current_offset=current_offset,
                    log_end_offset=log_end_offset,
                    lag=lag,
                )
            )

        if not partition_lags:
            return _create_error_result(
                consumer_group,
                topic,
                "Could not compute lag for any partitions. "
                "This may indicate authorization issues or broker problems.",
            )

        # Sort by highest lag first
        partition_lags.sort(key=lambda x: x.lag, reverse=True)

        return ConsumerLagResult(
            consumer_group=consumer_group,
            topic=topic,
            total_lag=total_lag,
            partition_count=len(partition_lags),
            partitions=partition_lags,
            error=None,
        )

    except KafkaException as e:
        err_msg = str(e)
        # Generic Kafka error handler
        return _create_error_result(
            consumer_group,
            topic,
            f"Kafka error: {err_msg}. "
            f"Please verify Kafka is running at {bootstrap_servers}",
        )
    except Exception as e:
        # Catch-all for unexpected errors
        return _create_error_result(
            consumer_group,
            topic,
            f"Unexpected error ({type(e).__name__}): {str(e)}",
        )


async def get_consumer_lag(
    consumer_group: str,
    topic: Optional[str] = None,
) -> ConsumerLagResult:
    """
    Get consumer group lag per partition using AdminClient only.

    This async wrapper runs the blocking Kafka operations in a thread pool
    to avoid blocking the event loop.

    Steps:
      1. Fetch committed offsets for the consumer group.
      2. For those partitions, fetch latest offsets.
      3. Compute lag = latest_offset - committed_offset per partition.
    """
    # Run blocking Kafka operations in a thread pool
    return await asyncio.to_thread(
        _fetch_consumer_lag_sync,
        consumer_group,
        topic,
    )



# This file implements the Kafka consumer lag check logic.
# It uses only the AdminClient API .
# We intentionally avoid creating a Kafka Consumer() to prevent rebalances.
# We get committed offsets using list_consumer_group_offsets().
# We get latest offsets using list_offsets() with OffsetSpec.latest().
# Lag is calculated as latest offset minus committed offset.
# The function provides partition-level lag breakdown and total lag.
# Kafka calls are synchronous, so we run them in a separate thread.
# The async get_consumer_lag() wrapper keeps the MCP server responsive.
# If Kafka is unreachable or offsets missing, we return structured error responses.
# Response always conforms to ConsumerLagResult, enabling consistent tool output.
# No scanning of all topics or consumer groups — this is efficient and targeted.


# Kafka library is blocking
# The confluent_kafka admin client does NOT support async.
# Our MCP server is async,if kafka operation blocks inside this leads to server stop responsing 
# so we use the threading we will run the slow, blocking Kafka operations in a separate worker thread and let the main async server continue working normally
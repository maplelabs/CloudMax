#!/usr/bin/env python3
"""Kafka Producer - Generate test data for consumer lag monitoring."""

import json
import time
import random
import argparse
from datetime import datetime
from confluent_kafka import Producer
from confluent_kafka.error import KafkaError


def delivery_report(err, msg):
    """Callback for message delivery status."""
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [partition {msg.partition()}] at offset {msg.offset()}")


def generate_test_message(message_id: int) -> dict:
    """Generate a test message."""
    return {
        "id": message_id,
        "timestamp": datetime.now().isoformat(),
        "amount": round(random.uniform(10, 1000), 2),
        "status": random.choice(["pending", "completed", "failed"]),
        "customer_id": f"CUST-{random.randint(1000, 9999)}",
        "transaction_type": random.choice(["payment", "refund", "transfer"]),
    }


def produce_messages(
    bootstrap_servers: str,
    topic: str,
    num_messages: int,
    interval: float = 0.1,
    batch_size: int = 1,
):
    """Produce messages to Kafka topic.
    
    Args:
        bootstrap_servers: Kafka bootstrap servers (e.g., "localhost:9092")
        topic: Topic name to produce to
        num_messages: Number of messages to produce
        interval: Delay between messages in seconds
        batch_size: Number of messages to produce before flushing
    """
    # Create producer config
    config = {
        "bootstrap.servers": bootstrap_servers,
        "client.id": "test-producer",
    }

    # Create producer
    producer = Producer(config)

    print(f"\n{'='*70}")
    print(f"Kafka Producer - Generating Test Data")
    print(f"{'='*70}")
    print(f"Bootstrap Servers: {bootstrap_servers}")
    print(f"Topic: {topic}")
    print(f"Messages to produce: {num_messages}")
    print(f"Interval between messages: {interval}s")
    print(f"Batch size: {batch_size}")
    print(f"{'='*70}\n")

    try:
        for i in range(num_messages):
            # Generate test message
            message = generate_test_message(i + 1)
            message_json = json.dumps(message)

            # Produce message
            producer.produce(
                topic=topic,
                key=str(message["customer_id"]).encode("utf-8"),
                value=message_json.encode("utf-8"),
                callback=delivery_report,
            )

            # Flush batch
            if (i + 1) % batch_size == 0:
                producer.flush()
                print(f"Flushed {i + 1}/{num_messages} messages")

            # Wait before next message
            if i < num_messages - 1:
                time.sleep(interval)

        # Final flush
        producer.flush()
        print(f"\nSuccessfully produced {num_messages} messages to topic '{topic}'")

    except KafkaError as e:
        print(f"Kafka error: {e}")
    except KeyboardInterrupt:
        print("\n Producer interrupted by user")
    finally:
        # Flush any remaining messages
        producer.flush()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Kafka Producer - Generate test data for consumer lag monitoring"
    )
    parser.add_argument(
        "--bootstrap-servers",
        default="localhost:9092",
        help="Kafka bootstrap servers (default: localhost:9092)",
    )
    parser.add_argument(
        "--topic",
        default="test-topic",
        help="Topic name to produce to (default: test-topic)",
    )
    parser.add_argument(
        "--messages",
        type=int,
        default=100,
        help="Number of messages to produce (default: 100)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="Delay between messages in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of messages to produce before flushing (default: 10)",
    )

    args = parser.parse_args()

    produce_messages(
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        num_messages=args.messages,
        interval=args.interval,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""Create consumer lag by consuming only a portion of messages."""

import argparse
import sys
from confluent_kafka import Consumer
from confluent_kafka.error import KafkaError


def create_consumer_lag(
    bootstrap_servers: str,
    topic: str,
    consumer_group: str,
    num_messages_to_consume: int,
):
    """Create consumer lag by consuming only a portion of messages.
    
    Args:
        bootstrap_servers: Kafka bootstrap servers
        topic: Topic name
        consumer_group: Consumer group ID
        num_messages_to_consume: Number of messages to consume (rest will be lag)
    """
    print(f"\n{'='*70}")
    print(f"📊 Creating Consumer Lag")
    print(f"{'='*70}")
    print(f"Bootstrap Servers: {bootstrap_servers}")
    print(f"Topic: {topic}")
    print(f"Consumer Group: {consumer_group}")
    print(f"Messages to consume: {num_messages_to_consume}")
    print(f"{'='*70}\n")

    try:
        # Create consumer with better configuration
        consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': consumer_group,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,  # Manual commit for better control
            'session.timeout.ms': 30000,  # Longer session timeout
            'heartbeat.interval.ms': 10000,  # Heartbeat interval
        })

        # Subscribe to topic
        consumer.subscribe([topic])

        # Wait for partition assignment
        print("Waiting for partition assignment...")
        for i in range(10):  # Try up to 10 times
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    break
                else:
                    print(f"{msg.error()}")
                    continue
            else:
                # Got a message, process it
                consumed = 1
                print(f"  Consumed message {consumed}: {msg.value()[:50]}...")
                consumer.commit()
                break

        # Consume remaining messages
        consumed = 0
        for i in range(num_messages_to_consume):
            msg = consumer.poll(2.0)  # Longer timeout
            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    print(f"Reached end of partition (consumed {consumed} messages)")
                    break
                else:
                    print(f"{msg.error()}")
                    continue

            consumed += 1
            print(f"  onsumed message {consumed}: {msg.value()[:50]}...")
            consumer.commit()

        # Close consumer
        consumer.close()
        
        print(f"\n{'='*70}")
        print(f"Consumer lag created!")
        print(f"{'='*70}")
        print(f"Messages consumed: {consumed}")
        print(f"Messages remaining (lag): {100 - consumed}")
        print(f"Consumer Group: {consumer_group}")
        print(f"Topic: {topic}")
        print(f"{'='*70}\n")
        
        print(f"Next step: Check lag with MCP client")
        print(f"   python3 multi_server_client.py {consumer_group} {topic}\n")
        
    except KafkaError as e:
        print(f"Kafka error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create consumer lag by consuming only a portion of messages"
    )
    parser.add_argument(
        "--bootstrap-servers",
        default="localhost:9092",
        help="Kafka bootstrap servers (default: localhost:9092)",
    )
    parser.add_argument(
        "--topic",
        default="test-topic",
        help="Topic name (default: test-topic)",
    )
    parser.add_argument(
        "--consumer-group",
        default="test-consumer-group",
        help="Consumer group ID (default: test-consumer-group)",
    )
    parser.add_argument(
        "--consume",
        type=int,
        default=10,
        help="Number of messages to consume (default: 10)",
    )

    args = parser.parse_args()

    create_consumer_lag(
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        consumer_group=args.consumer_group,
        num_messages_to_consume=args.consume,
    )


if __name__ == "__main__":
    main()


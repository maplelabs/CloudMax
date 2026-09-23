#!/usr/bin/env python3
"""Complete MCP Server Workflow - Automated Setup & Testing."""

import subprocess
import time
import sys
from confluent_kafka import Consumer


class Colors:
    """ANSI color codes."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'


def print_header():
    """Print workflow header."""
    print(f"\n{Colors.BLUE}╔════════════════════════════════════════════════════════════════╗{Colors.NC}")
    print(f"{Colors.BLUE}║                                                                ║{Colors.NC}")
    print(f"{Colors.BLUE}║     🚀 MCP Server Complete Workflow - Automated Setup         ║{Colors.NC}")
    print(f"{Colors.BLUE}║                                                                ║{Colors.NC}")
    print(f"{Colors.BLUE}╚════════════════════════════════════════════════════════════════╝{Colors.NC}\n")


def run_command(cmd, description):
    """Run a shell command."""
    print(f"{Colors.YELLOW}[*]{Colors.NC} {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=False)
        print(f"{Colors.GREEN}✅ {description}{Colors.NC}\n")
        return result
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}❌ {description} failed: {e}{Colors.NC}\n")
        raise


def cleanup_existing_processes():
    """Kill any existing MCP server processes."""
    print(f"{Colors.YELLOW}[Cleanup] Killing any existing MCP server processes...{Colors.NC}")
    subprocess.run("pkill -f 'run_mcp_server.py' || true", shell=True, check=False, capture_output=True)
    time.sleep(1)


def start_kafka():
    """Step 1: Start Kafka."""
    print(f"{Colors.YELLOW}[Step 1/5]{Colors.NC} Starting Kafka...")
    subprocess.run("docker compose up -d", shell=True, check=True, capture_output=True)
    time.sleep(3)
    print(f"{Colors.GREEN}✅ Kafka started{Colors.NC}\n")


def start_mcp_server():
    """Step 2: Start MCP Server."""
    print(f"{Colors.YELLOW}[Step 2/5]{Colors.NC} Starting MCP Server (auto-detecting SSL)...")
    proc = subprocess.Popen(
        "python3 run_mcp_server.py",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(3)
    print(f"{Colors.GREEN}✅ MCP Server started (PID: {proc.pid}){Colors.NC}\n")
    return proc


def generate_test_data(num_messages=100):
    """Step 3: Generate test data."""
    print(f"{Colors.YELLOW}[Step 3/5]{Colors.NC} Generating test data ({num_messages} messages)...")
    subprocess.run(
        f"python3 kafka_producer.py --messages {num_messages} --interval 0.05",
        shell=True,
        check=True
    )
    print(f"{Colors.GREEN}✅ Test data generated{Colors.NC}\n")


def create_consumer_lag(consume_messages=10):
    """Step 4: Create consumer lag."""
    print(f"{Colors.YELLOW}[Step 4/5]{Colors.NC} Creating consumer lag (consuming {consume_messages} messages)...")
    
    try:
        consumer = Consumer({
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'test-consumer-group',
            'auto.offset.reset': 'earliest'
        })
        consumer.subscribe(['test-topic'])
        
        consumed = 0
        for i in range(consume_messages):
            msg = consumer.poll(1.0)
            if msg:
                consumed += 1
                print(f"  Consumed message {consumed}")
                consumer.commit()
        
        consumer.close()
        lag = 100 - consumed
        print(f"{Colors.GREEN}✅ Consumer stopped - lag created! ({lag} messages behind){Colors.NC}\n")
    except Exception as e:
        print(f"{Colors.RED}❌ Error creating consumer lag: {e}{Colors.NC}\n")
        raise


def check_lag_with_client():
    """Step 5: Check lag with MCP client."""
    print(f"{Colors.YELLOW}[Step 5/5]{Colors.NC} Checking lag with MCP client...\n")
    subprocess.run(
        "python3 multi_server_client.py test-consumer-group test-topic",
        shell=True,
        check=True
    )
    print()


def stop_services(mcp_pid):
    """Stop MCP server and Kafka."""
    print(f"\n{Colors.YELLOW}[Cleanup] Stopping services...{Colors.NC}\n")

    try:
        # Stop MCP server
        print(f"  Stopping MCP server (PID: {mcp_pid})...")
        subprocess.run(f"kill {mcp_pid}", shell=True, check=False)
        time.sleep(1)
        print(f"  {Colors.GREEN}✅ MCP server stopped{Colors.NC}")

        # Stop Kafka
        print(f"  Stopping Kafka...")
        subprocess.run("docker compose down", shell=True, check=False, capture_output=True)
        print(f"  {Colors.GREEN}✅ Kafka stopped{Colors.NC}\n")
    except Exception as e:
        print(f"  {Colors.RED}⚠️  Error during cleanup: {e}{Colors.NC}\n")


def print_footer(mcp_pid):
    """Print workflow footer."""
    print(f"{Colors.BLUE}════════════════════════════════════════════════════════════════{Colors.NC}")
    print(f"{Colors.GREEN}✅ Workflow completed successfully!{Colors.NC}\n")
    print(f"{Colors.YELLOW}To stop the MCP server:{Colors.NC}")
    print(f"  kill {mcp_pid}\n")
    print(f"{Colors.YELLOW}To stop Kafka:{Colors.NC}")
    print(f"  docker compose down\n")
    print(f"{Colors.YELLOW}To stop all services automatically:{Colors.NC}")
    print(f"  Press Ctrl+C in this terminal\n")


def main():
    """Main workflow."""
    mcp_proc = None
    try:
        print_header()

        # Cleanup: Kill any existing processes
        cleanup_existing_processes()

        # Step 1: Start Kafka
        start_kafka()

        # Step 2: Start MCP Server
        mcp_proc = start_mcp_server()

        # Step 3: Generate test data
        generate_test_data(num_messages=100)

        # Step 4: Create consumer lag
        create_consumer_lag(consume_messages=10)

        # Step 5: Check lag with client
        check_lag_with_client()

        # Print footer
        print_footer(mcp_proc.pid)

        # Ask user if they want to stop services
        print(f"{Colors.YELLOW}Do you want to stop all services now? (y/n): {Colors.NC}", end="")
        response = input().strip().lower()

        if response == 'y':
            stop_services(mcp_proc.pid)
            print(f"{Colors.GREEN}✅ All services stopped{Colors.NC}\n")
        else:
            print(f"\n{Colors.YELLOW}Services are still running. Stop them manually when done:{Colors.NC}")
            print(f"  kill {mcp_proc.pid}")
            print(f"  docker compose down\n")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Workflow interrupted by user{Colors.NC}\n")
        if mcp_proc:
            print(f"{Colors.YELLOW}Stopping services...{Colors.NC}")
            stop_services(mcp_proc.pid)
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Workflow failed: {e}{Colors.NC}\n")
        if mcp_proc:
            print(f"{Colors.YELLOW}Stopping services...{Colors.NC}")
            stop_services(mcp_proc.pid)
        sys.exit(1)


if __name__ == "__main__":
    main()


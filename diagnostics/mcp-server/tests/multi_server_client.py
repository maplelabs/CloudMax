#!/usr/bin/env python3
"""Multi-Server MCP Client with mTLS Support.

This client connects to multiple MCP servers using MultiServerMCPClient
and supports mTLS (mutual TLS) for secure communication.

Usage:
    python3 multi_server_client.py [--ssl] [consumer_group] [topic]
"""

import argparse
import asyncio
import ssl
import sys
from pathlib import Path
from typing import Optional
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient


def extract_cn_from_cert(cert_path: str) -> Optional[str]:
    """Extract Common Name (CN) from a certificate.

    Args:
        cert_path: Path to the certificate file

    Returns:
        Common Name (CN) from the certificate, or None if not found
    """
    try:
        with open(cert_path, 'rb') as f:
            cert_data = f.read()

        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Extract CN from Subject
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                return attr.value

        return None
    except Exception as e:
        print(f"Error extracting CN from {cert_path}: {e}")
        return None


def create_ssl_context(
    ca_cert: str,
    client_cert: str,
    client_key: str,
    verify: bool = True
) -> ssl.SSLContext:
    """Create SSL context for mTLS connections.

    Args:
        ca_cert: Path to CA certificate
        client_cert: Path to client certificate
        client_key: Path to client private key
        verify: Whether to verify server certificate

    Returns:
        Configured SSL context
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # Load client certificate and key
    context.load_cert_chain(
        certfile=client_cert,
        keyfile=client_key
    )

    # Load CA certificate for server verification
    context.load_verify_locations(ca_cert)

    # Require certificate verification
    context.verify_mode = ssl.CERT_REQUIRED if verify else ssl.CERT_NONE

    return context


def create_httpx_client(
    use_mtls: bool = False,
    ca_cert: Optional[str] = None,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None
) -> httpx.AsyncClient:
    """Create httpx client with optional mTLS support.

    Args:
        use_mtls: Whether to use mTLS
        ca_cert: Path to CA certificate
        client_cert: Path to client certificate
        client_key: Path to client private key

    Returns:
        Configured httpx AsyncClient
    """
    if use_mtls and ca_cert and client_cert and client_key:
        ssl_context = create_ssl_context(ca_cert, client_cert, client_key)
        return httpx.AsyncClient(verify=ssl_context)
    else:
        return httpx.AsyncClient(verify=False)


async def main():
    """Main function to demonstrate multi-server MCP client."""

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Multi-Server MCP Client with optional mTLS support"
    )
    parser.add_argument(
        "consumer_group",
        nargs="?",
        default="test-consumer-group",
        help="Consumer group to check (default: test-consumer-group)"
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="test-topic",
        help="Topic to check (default: test-topic)"
    )
    parser.add_argument(
        "--ssl",
        action="store_true",
        help="Enable mTLS (requires certificates in certs/ directory)"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Multi-Server MCP Client with Optional mTLS")
    print("=" * 80)
    print()

    # Certificate paths
    certs_dir = Path("certs")
    ca_cert = str(certs_dir / "ca-cert.pem")
    client_cert = str(certs_dir / "client-cert.pem")
    client_key = str(certs_dir / "client-key.pem")

    # Check if certificates exist
    has_all_certs = all(Path(cert).exists() for cert in [ca_cert, client_cert, client_key])

    # Use mTLS only if --ssl flag is set AND certificates exist
    use_mtls = args.ssl and has_all_certs

    if use_mtls:
        print("mTLS enabled - using HTTPS with certificates from certs/")
        print()

        # Extract and display certificate CNs
        print("=" * 80)
        print("Certificate Information")
        print("=" * 80)

        client_cn = extract_cn_from_cert(client_cert)
        server_cn = extract_cn_from_cert(str(certs_dir / "server-cert.pem"))
        ca_cn = extract_cn_from_cert(ca_cert)

        print(f"Client Certificate CN: {client_cn if client_cn else 'N/A'}")
        print(f"Server Certificate CN: {server_cn if server_cn else 'N/A'}")
        print(f"CA Certificate CN: {ca_cn if ca_cn else 'N/A'}")
        print()
        print("=" * 80)
        print()
    elif args.ssl and not has_all_certs:
        print("⚠️  mTLS requested but certificates not found!")
        print("Using HTTP instead. To enable mTLS:")
        print("  1. Generate certificates: bash generate_certificates.sh")
        print("  2. Run with: python3 multi_server_client.py --ssl")
        print()
    else:
        print("mTLS disabled - using HTTP")
        print("To enable mTLS, run with: python3 multi_server_client.py --ssl")
        print()

    # Create httpx client factory
    def httpx_client_factory(**kwargs):
        """Factory function to create httpx client with optional mTLS.

        Accepts keyword arguments from langchain_mcp_adapters but ignores them
        to use our custom SSL configuration.
        """
        if use_mtls:
            return create_httpx_client(
                use_mtls=True,
                ca_cert=ca_cert,
                client_cert=client_cert,
                client_key=client_key
            )
        else:
            return create_httpx_client(use_mtls=False)

    # Configure multiple MCP servers (auto-detect protocol)
    protocol = "https" if use_mtls else "http"

    connections = {
        "kafka_lag_server": {
            "transport": "streamable_http",
            "url": f"{protocol}://localhost:8000/mcp",
            "httpx_client_factory": httpx_client_factory,
        }
    }

    try:
        # Create multi-server client
        print("[Step 1] Creating MultiServerMCPClient...")
        client = MultiServerMCPClient(connections)
        print("Client created")
        print()

        # Get tools from all servers
        print("[Step 2] Fetching tools from all servers...")
        all_tools = await client.get_tools()
        print(f"Found {len(all_tools)} tool(s)")
        print()

        # Display tools
        print("=" * 80)
        print("Available Tools")
        print("=" * 80)
        for i, tool in enumerate(all_tools, 1):
            print(f"\n{i}. {tool.name}")
            print(f"   Description: {tool.description}")

        print()

        # Step 3: Call the tool
        print("=" * 80)
        print("[Step 3] Calling get_consumer_lag_tool...")
        print("=" * 80)
        print()

        # Use parsed arguments
        consumer_group = args.consumer_group
        topic = args.topic

        print(f"Parameters:")
        print(f"  consumer_group: '{consumer_group}'")
        print(f"  topic: '{topic}'")
        print()

        # Find the get_consumer_lag_tool in the tools list
        lag_tool = next((t for t in all_tools if t.name == "get_consumer_lag_tool"), None)

        if not lag_tool:
            print("Error: get_consumer_lag_tool not found!")
            sys.exit(1)

        # Call the tool using ainvoke
        result = await lag_tool.ainvoke({
            "consumer_group": consumer_group,
            "topic": topic
        })

        print("Tool executed successfully!")
        print()

        # Display response
        print("=" * 80)
        print("CONSUMER LAG RESULT")
        print("=" * 80)
        print()

        import json
        if isinstance(result, str):
            result_data = json.loads(result)
        else:
            result_data = result

        print(json.dumps(result_data, indent=2))
        print()

        # Display summary
        if result_data.get("error"):
            print("Error:", result_data["error"])
        else:
            print("=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Consumer Group: {result_data.get('consumer_group')}")
            print(f"Topic: {result_data.get('topic', 'All topics')}")
            print(f"Total Lag: {result_data.get('total_lag')} messages")
            print(f"Partitions: {result_data.get('partition_count')}")
            print()

            if result_data.get('partitions'):
                print("Per-Partition Lag:")
                for partition in result_data['partitions']:
                    print(f"  Partition {partition['partition']}: "
                          f"lag={partition['lag']}, "
                          f"current_offset={partition['current_offset']}, "
                          f"log_end_offset={partition['log_end_offset']}")

        print()
        print("=" * 80)
        print("Multi-Server MCP Client working successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


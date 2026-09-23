"""
MCP Server with Direct mTLS and OPA Authorization
Combines direct TLS handling (no nginx) with OPA policy enforcement
"""
 
import sys
import os
import logging
import argparse
import ssl
from pathlib import Path
 
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
 
from fastmcp import FastMCP

from src.tools.get_consumer_lag import get_consumer_lag
from src.tools.db_check_access import check_access
from src.tools.db_check_locks import check_write_locks
from src.tools.db_check_connections import check_max_connections
from src.models.consumer_lag import ConsumerLagResult
from src.models.postgres_diagnostics import (
    CheckAccessResult,
    CheckWriteLocksResult,
    CheckMaxConnectionsResult,
)
from src.config.settings import settings
from src.middleware.opa_middleware import OPAAuthorizationMiddleware
 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
 
# Initialize FastMCP server
mcp = FastMCP("Diagnostic MCP Server")
 
# Conditionally add OPA authorization middleware based on MTLS_ENABLED flag
# When MTLS_ENABLED=true: Nginx (mTLS) → OPA (Authorization) → MCP Server → Tool
# When MTLS_ENABLED=false: Direct access → MCP Server → Tool (no authentication/authorization)
MTLS_ENABLED = os.getenv("MTLS_ENABLED", "true").lower() == "true"
if MTLS_ENABLED:
    logger.info("🔐 mTLS Mode: ENABLED - Nginx + OPA authorization required")
    try:
        mcp.add_middleware(OPAAuthorizationMiddleware(
            opa_url=os.getenv("OPA_URL", "http://localhost:8181")
        ))
        logger.info("✅ OPA middleware enabled (FastMCP 2.9+ API)")
    except Exception as e:
        logger.error(f"❌ Could not add OPA middleware: {e}")
        raise
else:
    logger.info("🔓 mTLS Mode: DISABLED - Direct access, no authentication/authorization")
 
 
@mcp.tool()
async def get_consumer_lag_tool(consumer_group: str, topic: str | None = None) -> ConsumerLagResult:
    """Get current Kafka consumer lag for a consumer group.

    Returns real-time lag information showing how far behind the consumer is from the latest messages.
    Provides per-partition lag breakdown and total lag across all partitions.

    Args:
        consumer_group: Kafka consumer group name (e.g., "my-consumer-group")
        topic: Optional topic filter. If None, returns lag for all topics consumed by the group

    Returns:
        ConsumerLagResult with partition-level lag details and total lag count

    Use this to:
    - Check current consumer lag (not historical trends)
    - Identify if consumer is falling behind
    - Diagnose processing delays
    """
    return await get_consumer_lag(consumer_group, topic)


@mcp.tool()
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "diagnostic-mcp-server",
        "kafka_bootstrap_servers": settings.kafka_bootstrap_servers
    }


# PostgreSQL Diagnostic Tools

@mcp.tool()
async def db_check_access_tool(database_url: str | None = None) -> CheckAccessResult:
    """Check if PostgreSQL database is currently reachable and accepting connections.

    Performs a simple connectivity test by executing SELECT 1 query.

    Args:
        database_url: Optional connection string. If not provided, uses default hotel-postgres settings
                      Format: postgresql://user:password@host:port/database

    Returns:
        CheckAccessResult with db_accessible=True if connection successful

    Use this to:
    - Verify database is up and accepting connections
    - Diagnose connection failures
    - Check network connectivity to database
    """
    return await check_access(database_url)


@mcp.tool()
async def db_check_write_locks_tool() -> CheckWriteLocksResult:
    """Check if the database currently has pending write locks.

    Queries pg_locks to find write operations that are waiting for locks.
    Pending write locks indicate contention issues or potential deadlocks.

    Checks these lock modes:
    - RowExclusiveLock (INSERT, UPDATE, DELETE)
    - ShareUpdateExclusiveLock (VACUUM, ANALYZE, CREATE INDEX CONCURRENTLY)
    - ShareRowExclusiveLock (CREATE TRIGGER)
    - ExclusiveLock (REFRESH MATERIALIZED VIEW CONCURRENTLY)
    - AccessExclusiveLock (DROP, ALTER, TRUNCATE)

    Returns:
        CheckWriteLocksResult with has_pending_locks=True if locks are waiting,
        includes details of each pending lock (PID, table, query)

    Use this to:
    - Diagnose database contention issues
    - Identify blocked write operations
    - Check for potential deadlocks
    """
    return await check_write_locks()


@mcp.tool()
async def db_check_max_connections_tool() -> CheckMaxConnectionsResult:
    """Check current active database connections vs maximum allowed connections.

    Queries pg_stat_activity to count active connections and compares against max_connections setting.

    Returns:
        CheckMaxConnectionsResult with:
        - active_connections: Current number of active connections
        - max_connections: Maximum allowed connections
        - utilization_percent: Percentage of connection pool used

    Use this to:
    - Check if database is running out of connections
    - Diagnose "too many connections" errors
    - Monitor connection pool utilization
    """
    return await check_max_connections()


def main() -> None:
    """Start the MCP server with direct mTLS and OPA authorization."""
    parser = argparse.ArgumentParser(description="MCP Server with Direct mTLS and OPA")
    parser.add_argument(
        "--ssl",
        action="store_true",
        help="Enable mTLS (requires certificates in certs/ directory)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        # default=8000,
        # help="Port to bind to (default: 8000)"
        default=8080,
        help="Port to bind to (default: 8080)"
    )
    args = parser.parse_args()
 
    # Configure SSL if requested
    uvicorn_config = {}
    protocol = "http"
 
    if args.ssl:
        cert_dir = Path("certs")
        server_cert = cert_dir / "server-cert.pem"
        server_key = cert_dir / "server-key.pem"
        ca_cert = cert_dir / "ca-cert.pem"
 
        # Check if certificates exist
        if not server_cert.exists() or not server_key.exists() or not ca_cert.exists():
            logger.error("SSL certificates not found!")
            logger.info("Please generate certificates first: ./generate_certificates.sh")
            logger.info("Or run without SSL: python src/main_fastmcp.py")
            return

        # Note: FastMCP handles SSL configuration internally via environment or other means
        # The certificates are validated at startup but SSL config is managed by FastMCP
        protocol = "https"
        logger.info("mTLS (Mutual TLS) enabled - client certificates required")
 
    logger.info(f"Starting Diagnostic MCP Server")
    logger.info(f"Transport: Streamable HTTP{'S' if args.ssl else ''}")
    logger.info(f"Host: {args.host}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Endpoint: /mcp")
    logger.info(f"Server URL: {protocol}://{args.host}:{args.port}/mcp")
    logger.info(f"mTLS: Controlled by backend database configuration (app_config.mcp_connections)")
 
    if args.ssl:
        logger.warning("Using mTLS - clients must present valid certificates")
        logger.info("Client requirements:")
        logger.info("  1. Trust CA certificate: certs/ca-cert.pem")
        logger.info("  2. Present client certificate signed by CA")
 
    logger.info("Press Ctrl+C to stop the server")

    # Run server with HTTP transport (streamable_http is the internal name, but use "http")
    # FastMCP accepts host and port directly as kwargs
    mcp.run(
        transport="http",
        host=args.host,
        port=args.port
    )
 
 
if __name__ == "__main__":
    main()
import logging
import os
import ssl
import tempfile
from datetime import timedelta
from typing import Optional, Dict

import httpx
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from src.server.models.api.enums import ObservabilitySystem
from src.server.utilities.config import should_use_database_config, load_config_from_db

logger = logging.getLogger(__name__)


def get_required_env_var(var_name: str) -> str:
    """Get required environment variable or raise error if not set."""
    value = os.environ.get(var_name)
    if not value:
        raise ValueError(
            f"Required environment variable {var_name} is not set")
    return value


def create_ssl_context(ca_cert: str, client_cert: str, client_key: str) -> tuple[ssl.SSLContext, list[str]]:
    """
    Create SSL context for mTLS connections.

    Args:
        ca_cert: CA certificate content (PEM format)
        client_cert: Client certificate content (PEM format)
        client_key: Client private key content (PEM format)

    Returns:
        Tuple of (SSL context, list of temporary file paths for cleanup)

    Note:
        The caller is responsible for cleaning up the temporary files after use.
        The files must remain on disk while the SSL context is being used by httpx.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # Write certificates to temporary files (required by ssl module)
    ca_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    ca_file.write(ca_cert)
    ca_file.flush()
    ca_file.close()

    cert_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    cert_file.write(client_cert)
    cert_file.flush()
    cert_file.close()

    key_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    key_file.write(client_key)
    key_file.flush()
    key_file.close()

    try:
        # Load client certificate and key
        context.load_cert_chain(
            certfile=cert_file.name,
            keyfile=key_file.name
        )
    except Exception as e:
        logger.error(f"Failed to load client cert chain: {e}")
        raise

    try:
        # Load CA certificate for server verification
        context.load_verify_locations(cafile=ca_file.name)
    except Exception as e:
        logger.error(f"Failed to load CA cert: {e}")
        raise

    # Verify server certificate using the CA cert, but don't check hostname
    # (we're using Docker service names like 'mcp-nginx' which don't match the cert CN)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED

    return context, [ca_file.name, cert_file.name, key_file.name]


def create_httpx_client_factory(ca_cert: Optional[str] = None,
                                client_cert: Optional[str] = None,
                                client_key: Optional[str] = None):
    """
    Create httpx client factory function with optional mTLS support.

    Args:
        ca_cert: CA certificate content (PEM format)
        client_cert: Client certificate content (PEM format)
        client_key: Client private key content (PEM format)

    Returns:
        Factory function that creates httpx AsyncClient

    Note:
        When mTLS is enabled, the SSL context is created ONCE when the factory is created,
        not every time the factory is called. This ensures temp certificate files remain
        alive for the lifetime of all clients created by this factory.
    """
    # Create SSL context ONCE at factory creation time (not per-client)
    ssl_context = None
    temp_files = []

    if ca_cert and client_cert and client_key:
        ssl_context, temp_files = create_ssl_context(ca_cert, client_cert, client_key)

    def factory(**kwargs):
        if ssl_context is not None:
            client = httpx.AsyncClient(verify=ssl_context, **kwargs)
            client._mtls_temp_files = temp_files
            return client
        else:
            return httpx.AsyncClient(**kwargs)

    factory._mtls_temp_files = temp_files
    factory._ssl_context = ssl_context

    return factory


async def get_mcp_connection(system_name: ObservabilitySystem) -> StreamableHttpConnection:
    """
    Get MCP connection for any observability system.
    Uses database configuration if CONFIG_DB=true, otherwise uses environment variables.
    Supports mTLS authentication when configured.

    Args:
        system_name: ObservabilitySystem enum value

    Returns:
        StreamableHttpConnection configured with optional mTLS support
    """
    system_url = None
    mtls_enabled = False
    ca_cert = None
    client_cert = None
    client_key = None

    system_name_str = system_name.value
    system_display_name = system_name_str.title()
    env_var_name = f"{system_name_str.upper()}_MCP_URL"

    if should_use_database_config():
        try:
            config = await load_config_from_db()
            if not config:
                raise ValueError(
                    f"CONFIG_DB=true but no database configuration found. Please configure MCP connections through the UI or set CONFIG_DB=false to use environment variables.")

            # Get MCP configuration
            mcp_config = config.get("mcp", {})
            system_url = mcp_config.get(f"{system_name_str}_url")

            if not system_url:
                raise ValueError(
                    f"CONFIG_DB=true but no {system_display_name} MCP configuration found in database. Please configure {system_display_name} MCP connection through the UI or set CONFIG_DB=false to use environment variables.")

            # Find the specific system connection configuration for mTLS settings
            connections = mcp_config.get("connections", [])
            for conn in connections:
                if conn.get("system") == system_name_str and conn.get("enabled"):
                    # mTLS settings are at the top level of conn, not inside connection_config
                    mtls_enabled = conn.get("mtls_enabled", True)
                    ca_cert = conn.get("ca_cert")
                    client_cert = conn.get("client_cert")
                    client_key = conn.get("client_key")
                    break



        except Exception as e:
            if "CONFIG_DB=true" in str(e):
                raise
            else:
                raise ValueError(
                    f"Failed to load {system_display_name} MCP config from database: {e}. Please configure through the UI or set CONFIG_DB=false to use environment variables.")
    else:
        # CONFIG_DB=false: Load from environment variables
        system_url = os.getenv(env_var_name)
        if not system_url:
            raise ValueError(
                f"{env_var_name} environment variable not set. Please set it or configure through the UI with CONFIG_DB=true.")

    # Create connection with optional mTLS support
    connection_kwargs = {
        "url": system_url,
        "transport": "streamable_http",
        "timeout": timedelta(seconds=300)
    }

    if mtls_enabled and ca_cert and client_cert and client_key:
        connection_kwargs["httpx_client_factory"] = create_httpx_client_factory(
            ca_cert=ca_cert,
            client_cert=client_cert,
            client_key=client_key
        )
    elif system_url and system_url.startswith("https://"):
        def create_insecure_client(**kwargs):
            import httpx
            return httpx.AsyncClient(verify=False, **kwargs)

        connection_kwargs["httpx_client_factory"] = create_insecure_client

    logger.info(f"Creating StreamableHttpConnection for {system_display_name} at {system_url} (mTLS: {mtls_enabled})")
    return StreamableHttpConnection(**connection_kwargs)


async def get_grafana_mcp_connection() -> StreamableHttpConnection:
    """Get Grafana MCP connection asynchronously."""
    return await get_mcp_connection(ObservabilitySystem.GRAFANA)


async def get_jaeger_mcp_connection() -> StreamableHttpConnection:
    """Get Jaeger MCP connection asynchronously."""
    return await get_mcp_connection(ObservabilitySystem.JAEGER)


async def get_opensearch_mcp_connection() -> StreamableHttpConnection:
    """Get OpenSearch MCP connection asynchronously."""
    return await get_mcp_connection(ObservabilitySystem.OPENSEARCH)


async def get_diagnostic_mcp_connections() -> Dict[str, StreamableHttpConnection]:
    """
    Get all enabled Diagnostic MCP server connections.
    Returns a dictionary mapping server names to their connections.
    Supports multiple diagnostic MCP servers with mTLS.

    Returns:
        Dict[str, StreamableHttpConnection]: Dictionary of diagnostic MCP connections
    """
    from src.server.utilities.config import load_config_from_db

    connections = {}

    # Check if using database config
    use_db_config = os.getenv("CONFIG_DB", "false").lower() == "true"

    if use_db_config:
        try:
            db_config = await load_config_from_db()
            if not db_config:
                return connections

            diagnostic_data = db_config.get("diagnostic_mcp")
            if not diagnostic_data or not isinstance(diagnostic_data, dict):
                return connections

            servers = diagnostic_data.get("servers", [])
            for server in servers:
                if not server.get("enabled", False):
                    continue

                server_name = server.get("name", "")
                # Config is already flattened by load_config_from_db()
                endpoint_url = server.get("endpoint_url", "")

                if not server_name or not endpoint_url:
                    logger.warning(f"Skipping diagnostic MCP server: missing name or endpoint_url")
                    continue

                # Extract mTLS configuration (already flattened)
                mtls_enabled = server.get("mtls_enabled", False)
                ca_cert = server.get("ca_cert")
                client_cert = server.get("client_cert")
                client_key = server.get("client_key")

                # Create connection with optional mTLS support
                connection_kwargs = {
                    "url": endpoint_url,
                    "transport": "streamable_http",
                    "timeout": timedelta(seconds=300)
                }

                if mtls_enabled and ca_cert and client_cert and client_key:
                    # Use the same factory pattern as observability systems
                    connection_kwargs["httpx_client_factory"] = create_httpx_client_factory(
                        ca_cert=ca_cert,
                        client_cert=client_cert,
                        client_key=client_key
                    )
                elif endpoint_url and endpoint_url.startswith("https://"):
                    # HTTPS without mTLS - disable SSL verification
                    def create_insecure_client(**kwargs):
                        import httpx
                        return httpx.AsyncClient(verify=False, **kwargs)

                    connection_kwargs["httpx_client_factory"] = create_insecure_client

                connections[server_name] = StreamableHttpConnection(**connection_kwargs)
                logger.info(f"Loaded diagnostic MCP server '{server_name}' from database (mTLS: {mtls_enabled})")

        except Exception as e:
            logger.error(f"Failed to load diagnostic MCP servers from database: {e}")
            raise
    else:
        # CONFIG_DB=false: Load from environment variable (single server for backward compatibility)
        diagnostic_url = os.getenv("DIAGNOSTIC_MCP_URL")
        if diagnostic_url:
            connections["Diagnostic"] = StreamableHttpConnection(
                url=diagnostic_url,
                transport="streamable_http",
                timeout=timedelta(seconds=300)
            )
            logger.info("Loaded diagnostic MCP server from DIAGNOSTIC_MCP_URL environment variable")

    return connections

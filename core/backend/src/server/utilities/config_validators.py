"""
Connection Validators - Reusable validation functions for all connection types
"""
import asyncio
import logging
import os
import ssl
import tempfile
import time
from datetime import timedelta
from typing import Optional

import httpx

from src.server.models.api.connection_test import ConnectionTestResponse

logger = logging.getLogger(__name__)


def create_ssl_context_for_validation(ca_cert: str, client_cert: str, client_key: str) -> tuple[ssl.SSLContext, list]:
    """
    Create SSL context for mTLS connection validation.

    Args:
        ca_cert: CA certificate content (PEM format)
        client_cert: Client certificate content (PEM format)
        client_key: Client private key content (PEM format)

    Returns:
        Tuple of (Configured SSL context, list of temp file paths to clean up later)
    """
    logger.info("Creating SSL context for mTLS validation")

    # Write certificates to temporary files (required by ssl module)
    # DON'T delete them yet - they need to exist during the SSL handshake
    ca_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    ca_file.write(ca_cert)
    ca_file.flush()
    ca_file.close()
    logger.info(f"Wrote CA cert to {ca_file.name} ({len(ca_cert)} bytes)")

    cert_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    cert_file.write(client_cert)
    cert_file.flush()
    cert_file.close()
    logger.info(f"Wrote client cert to {cert_file.name} ({len(client_cert)} bytes)")

    key_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    key_file.write(client_key)
    key_file.flush()
    key_file.close()
    logger.info(f"Wrote client key to {key_file.name} ({len(client_key)} bytes)")

    # Create SSL context
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    # Load CA certificate for server verification FIRST
    context.load_verify_locations(ca_file.name)
    logger.info("Loaded CA certificate for server verification")

    # Load client certificate and key
    context.load_cert_chain(
        certfile=cert_file.name,
        keyfile=key_file.name
    )
    logger.info("Loaded client certificate and key")

    # Verify server certificate using the CA cert, but don't check hostname
    # (we're using Docker service names like 'mcp-nginx' which don't match the cert CN)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    logger.info("SSL context configured successfully (server cert verification enabled)")

    # Return context and file paths for later cleanup
    return context, [ca_file.name, cert_file.name, key_file.name]


async def validate_mcp_connection(
        system_name: str,
        endpoint_url: str,
        enabled: bool,
        mtls_enabled: bool = False,
        ca_cert: Optional[str] = None,
        client_cert: Optional[str] = None,
        client_key: Optional[str] = None
):
    """
    Generic MCP connection validation for any MCP system (Grafana, Jaeger, etc.)
    Supports mTLS authentication when configured.

    Args:
        system_name: Name of the system (e.g., "Grafana", "Jaeger")
        endpoint_url: MCP endpoint URL
        enabled: Whether the connection is enabled
        mtls_enabled: Whether mTLS is enabled
        ca_cert: CA certificate content (PEM format)
        client_cert: Client certificate content (PEM format)
        client_key: Client private key content (PEM format)

    Returns:
        ConnectionTestResponse with validation results
    """
    start_time = time.time()

    logger.info(f"=== MCP Connection Validation for {system_name} ===")
    logger.info(f"Endpoint URL: {endpoint_url}")
    logger.info(f"mTLS Enabled: {mtls_enabled}")
    logger.info(f"CA Cert provided: {bool(ca_cert)} ({len(ca_cert) if ca_cert else 0} bytes)")
    logger.info(f"Client Cert provided: {bool(client_cert)} ({len(client_cert) if client_cert else 0} bytes)")
    logger.info(f"Client Key provided: {bool(client_key)} ({len(client_key) if client_key else 0} bytes)")

    try:
        if not enabled:
            return ConnectionTestResponse(
                success=False,
                message=f"{system_name} system is disabled",
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        if not endpoint_url or not endpoint_url.strip():
            return ConnectionTestResponse(
                success=False,
                message="MCP endpoint URL is required",
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        # Sanitize and validate URL
        endpoint_url = endpoint_url.strip()

        # Remove trailing slashes for consistency
        endpoint_url = endpoint_url.rstrip('/')

        # Validate URL format
        from urllib.parse import urlparse
        try:
            parsed = urlparse(endpoint_url)
            if not parsed.scheme or not parsed.netloc:
                return ConnectionTestResponse(
                    success=False,
                    message=f"Invalid URL format: '{endpoint_url}'. URL must include scheme (http/https) and host.",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            # Validate scheme
            if parsed.scheme not in ['http', 'https']:
                return ConnectionTestResponse(
                    success=False,
                    message=f"Invalid URL scheme: '{parsed.scheme}'. Only 'http' and 'https' are supported.",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            # Warn about unusual paths (but still try to connect to see actual error)
            if parsed.path and parsed.path not in ['/', '/mcp']:
                logger.warning(f"Unusual MCP endpoint path: '{parsed.path}'. Expected '/mcp'. URL: {endpoint_url}")
                logger.warning(f"Will attempt connection - if it fails, try: {parsed.scheme}://{parsed.netloc}/mcp")

        except Exception as e:
            return ConnectionTestResponse(
                success=False,
                message=f"Invalid URL format: {str(e)}",
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        # Auto-correct http:// to https:// for port 8443 (common HTTPS port)
        if endpoint_url.startswith("http://") and ":8443" in endpoint_url:
            endpoint_url = endpoint_url.replace("http://", "https://", 1)
            logger.info(f"Auto-corrected URL from http:// to https:// for port 8443: {endpoint_url}")

        # Validate mTLS configuration if enabled
        if mtls_enabled:
            if not ca_cert or not client_cert or not client_key:
                return ConnectionTestResponse(
                    success=False,
                    message="mTLS is enabled but certificates are missing",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

        # Use MCP protocol for testing
        temp_files = []
        try:
            from langchain_mcp_adapters.sessions import StreamableHttpConnection
            from langchain_mcp_adapters.client import MultiServerMCPClient

            # Create connection kwargs
            connection_kwargs = {
                "url": endpoint_url,  # Already stripped and corrected above
                "transport": "streamable_http",
                "timeout": timedelta(seconds=10)
            }

            # Add httpx_client_factory if mTLS is enabled
            if mtls_enabled and ca_cert and client_cert and client_key:
                logger.info("Creating mTLS-enabled httpx client for connection test")
                ssl_context, temp_files = create_ssl_context_for_validation(ca_cert, client_cert, client_key)

                def httpx_client_factory(**kwargs):
                    """Factory function to create httpx client with mTLS."""
                    # Pass the SSL context directly to httpx
                    return httpx.AsyncClient(verify=ssl_context, **kwargs)

                connection_kwargs["httpx_client_factory"] = httpx_client_factory
                logger.info("httpx_client_factory configured with mTLS")
            elif endpoint_url.startswith("https://"):
                # For HTTPS without mTLS, disable SSL verification
                logger.info("Creating insecure httpx client for HTTPS without mTLS")

                def create_insecure_client(**kwargs):
                    return httpx.AsyncClient(verify=False, **kwargs)

                connection_kwargs["httpx_client_factory"] = create_insecure_client
                logger.info("httpx_client_factory configured with verify=False")

            # Create StreamableHttpConnection using proper MCP protocol
            mcp_connection = StreamableHttpConnection(**connection_kwargs)

            # Test the connection using MultiServerMCPClient like the agents do
            mcp_client_config = {system_name: mcp_connection}
            mcp_client = MultiServerMCPClient(mcp_client_config)

            # Try to get tools (this tests the full MCP connection)
            # Wrap in asyncio.wait_for to enforce timeout
            logger.info(f"Attempting to fetch tools from MCP endpoint: {endpoint_url}")
            try:
                tools = await asyncio.wait_for(
                    mcp_client.get_tools(namespaced_tools=True),
                    timeout=10.0  # 10 second timeout
                )
                logger.info(f"Successfully fetched {len(tools) if tools else 0} tools from MCP endpoint")
            except asyncio.TimeoutError:
                logger.error(f"Connection timed out after 10 seconds for endpoint: {endpoint_url}")
                raise Exception(
                    f"Connection timed out after 10 seconds. The MCP endpoint '{endpoint_url}' may be incorrect or unreachable. Expected path is '/mcp'.")
            except Exception as e:
                logger.error(f"Failed to fetch tools from MCP endpoint: {endpoint_url}, error: {str(e)}")
                raise Exception(
                    f"Failed to connect to MCP endpoint '{endpoint_url}': {str(e)}. Verify the URL path is '/mcp'.")

            # Validate that we actually got tools
            if not tools or len(tools) == 0:
                logger.error(f"MCP endpoint returned 0 tools. URL may be incorrect: {endpoint_url}")
                raise Exception(
                    f"Connected to MCP endpoint but received 0 tools. The endpoint '{endpoint_url}' may be incorrect. Expected path is '/mcp'.")

            logger.info(f"MCP connection validation successful: {len(tools)} tools found")
            mtls_status = " (mTLS enabled)" if mtls_enabled else ""
            return ConnectionTestResponse(
                success=True,
                message=f"Successfully connected to {system_name} MCP{mtls_status} - Found {len(tools)} tools",
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        except Exception as mcp_error:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"MCP {system_name} connection test failed: {error_details}")
            return ConnectionTestResponse(
                success=False,
                message=f"MCP {system_name} connection failed: {str(mcp_error)}",
                response_time_ms=int((time.time() - start_time) * 1000)
            )
        finally:
            # Clean up temporary certificate files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass  # Ignore cleanup errors

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"MCP connection validation failed: {error_details}")
        return ConnectionTestResponse(
            success=False,
            message=f"MCP connection validation failed: {str(e)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )


async def validate_aws_bedrock_connection(api_key: str, region: str, model_id: str):
    """
    Validate AWS Bedrock connection by performing a real InvokeModel call.

    Args:
        api_key: AWS API key (can be empty if using other auth methods)
        region: AWS region (e.g., "us-east-1")
        model_id: Bedrock model ID (e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0")

    Returns:
        ConnectionTestResponse with validation results
    """
    start_time = time.time()

    # Basic required-field check
    missing = []
    if not region: missing.append("region")
    if not model_id: missing.append("model_id")
    if missing:
        return ConnectionTestResponse(
            success=False,
            message=f"AWS Bedrock missing required fields: {', '.join(missing)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )

    try:
        # Import boto3 and handle import errors
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
        except ImportError:
            return ConnectionTestResponse(
                success=False,
                message="boto3 library not installed. Install with: pip install boto3",
                response_time_ms=int((time.time() - start_time) * 1000)
            )

        # Prepare a minimal test message using the converse API format
        test_messages = [
            {
                "role": "user",
                "content": [{"text": "Test connection — reply 'ok'."}]
            }
        ]

        # Wrap blocking boto3 call in a thread
        def call_converse():
            # Create bedrock-runtime client with bearer token if provided
            if api_key and api_key.strip():
                os.environ['AWS_BEARER_TOKEN_BEDROCK'] = api_key.strip()

            client = boto3.client("bedrock-runtime", region_name=region)

            # Use the converse API (newer, more standardized)
            response = client.converse(
                modelId=model_id,
                messages=test_messages
            )
            return response

        # Run the blocking call in a thread
        response = await asyncio.to_thread(call_converse)

        # Extract response content
        if "output" in response and "message" in response["output"]:
            output_message = response["output"]["message"]
            content = output_message.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text_content = content[0].get("text", "")
                message = f"AWS Bedrock connection successful - Model replied: '{text_content}'"
            else:
                message = f"AWS Bedrock connection successful - Model responded with structure: {list(response.keys())}"
        else:
            message = f"AWS Bedrock connection successful - Response structure: {list(response.keys())}"

        return ConnectionTestResponse(
            success=True,
            message=message,
            response_time_ms=int((time.time() - start_time) * 1000)
        )

    except NoCredentialsError:
        return ConnectionTestResponse(
            success=False,
            message="AWS credentials not found. Configure AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY environment variables or AWS credentials file.",
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    except EndpointConnectionError as e:
        return ConnectionTestResponse(
            success=False,
            message=f"Cannot connect to AWS Bedrock endpoint in region '{region}': {str(e)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    except ClientError as e:
        # Extract AWS error details
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        return ConnectionTestResponse(
            success=False,
            message=f"AWS Bedrock error ({error_code}): {error_message}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    except Exception as e:
        return ConnectionTestResponse(
            success=False,
            message=f"AWS Bedrock connection failed: {str(e)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )


async def validate_azure_anthropic_connection(endpoint_url: str, api_key: str, model_id: str):
    """
    Validate Azure Anthropic (Claude on Azure AI Foundry) connection by performing a real API call.

    Args:
        endpoint_url: Azure AI Foundry endpoint URL (e.g., "https://resource.services.ai.azure.com/anthropic/v1/messages")
        api_key: Azure API key for Anthropic models
        model_id: Model deployment name (e.g., "claude-haiku-4-5")

    Returns:
        ConnectionTestResponse with validation results
    """
    import aiohttp

    start_time = time.time()

    # Basic required-field check
    missing = []
    if not endpoint_url:
        missing.append("endpoint_url")
    if not api_key:
        missing.append("api_key")
    if not model_id:
        missing.append("model_id")
    if missing:
        return ConnectionTestResponse(
            success=False,
            message=f"Azure Anthropic missing required fields: {', '.join(missing)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )

    try:
        # Normalize the endpoint URL - ensure it ends with /v1/messages
        normalized_url = endpoint_url.rstrip("/")
        if not normalized_url.endswith("/v1/messages"):
            if normalized_url.endswith("/v1"):
                normalized_url += "/messages"
            elif normalized_url.endswith("/anthropic"):
                normalized_url += "/v1/messages"
            else:
                normalized_url += "/v1/messages"

        # Prepare test request
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }

        test_payload = {
            "model": model_id,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Test connection - reply 'ok'."}]
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(normalized_url, headers=headers, json=test_payload) as response:
                response_time_ms = int((time.time() - start_time) * 1000)

                if response.status == 200:
                    # Parse response to get model reply
                    try:
                        response_data = await response.json()
                        content = response_data.get("content", [])
                        if content and isinstance(content, list) and len(content) > 0:
                            text_content = content[0].get("text", "")
                            message = f"Azure Anthropic connection successful - Model replied: '{text_content}'"
                        else:
                            message = "Azure Anthropic connection successful"
                    except Exception:
                        message = "Azure Anthropic connection successful"

                    return ConnectionTestResponse(
                        success=True,
                        message=message,
                        response_time_ms=response_time_ms
                    )
                elif response.status == 401:
                    return ConnectionTestResponse(
                        success=False,
                        message="Azure Anthropic authentication failed - invalid API key",
                        response_time_ms=response_time_ms
                    )
                elif response.status == 404:
                    return ConnectionTestResponse(
                        success=False,
                        message=f"Azure Anthropic model '{model_id}' not found or endpoint URL is invalid",
                        response_time_ms=response_time_ms
                    )
                else:
                    error_text = await response.text()
                    return ConnectionTestResponse(
                        success=False,
                        message=f"Azure Anthropic returned status {response.status}: {error_text[:200]}",
                        response_time_ms=response_time_ms
                    )

    except asyncio.TimeoutError:
        return ConnectionTestResponse(
            success=False,
            message="Azure Anthropic connection timed out after 30 seconds",
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    except aiohttp.ClientConnectorError as e:
        return ConnectionTestResponse(
            success=False,
            message=f"Cannot connect to Azure Anthropic endpoint: {str(e)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    except Exception as e:
        return ConnectionTestResponse(
            success=False,
            message=f"Azure Anthropic connection failed: {str(e)}",
            response_time_ms=int((time.time() - start_time) * 1000)
        )

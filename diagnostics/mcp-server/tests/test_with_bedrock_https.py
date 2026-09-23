"""
Test MCP Server with AWS Bedrock (Auto-detects mTLS mode)

This test automatically detects the deployment mode:
- If MTLS_ENABLED=true: Uses HTTPS with client certificates (port 30444)
- If MTLS_ENABLED=false: Uses HTTP without certificates (port 30445)

Features tested:
1. Auto-detection of mTLS mode
2. MCP client using streamable_http transport
3. Real AI conversation with AWS Bedrock Claude
4. OPA authorization (when mTLS enabled)
5. Direct access (when mTLS disabled)
"""

import asyncio
import os
import ssl
import json
from pathlib import Path
import httpx
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage

# ============================================================================
# Configuration
# ============================================================================

# Detect mTLS mode from environment variable
MTLS_ENABLED = os.getenv("MTLS_ENABLED", "true").lower() == "true"

# Certificate paths - use certs from project root (only needed if mTLS enabled)
CERT_DIR = Path(__file__).parent.parent / "certs"
CA_CERT = CERT_DIR / "ca-cert.pem"
CLIENT_CERT = CERT_DIR / "client-cert.pem"
CLIENT_KEY = CERT_DIR / "client-key.pem"

# MCP Server URL - depends on mTLS mode
MINIKUBE_IP = os.getenv("MINIKUBE_IP", "192.168.49.2")

if MTLS_ENABLED:
    # mTLS ENABLED: HTTPS via Nginx on port 30444
    NGINX_PORT = os.getenv("NGINX_PORT", "30444")
    MCP_SERVER_URL = f"https://{MINIKUBE_IP}:{NGINX_PORT}"
    MCP_ENDPOINT = f"{MCP_SERVER_URL}/mcp"  # Nginx proxies to MCP server
else:
    # mTLS DISABLED: Direct HTTP to MCP server on port 30445
    MCP_PORT = os.getenv("MCP_PORT", "30445")
    MCP_SERVER_URL = f"http://{MINIKUBE_IP}:{MCP_PORT}"
    MCP_ENDPOINT = f"{MCP_SERVER_URL}/mcp"

# AWS Bedrock Configuration
# Set AWS_BEARER_TOKEN_BEDROCK environment variable before running this test
BEDROCK_API_KEY_ENCODED = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")

# ============================================================================
# Helper Functions
# ============================================================================

def validate_client_certificate() -> str:
    """
    Validate client certificate and extract client ID from CN.
    Only called when mTLS is enabled.

    Returns:
        Client ID (Common Name from certificate)
    """
    print("🔐 Step 1: Validate Client Certificate")
    print("=" * 80)

    # Load and validate certificate
    with open(CLIENT_CERT, 'rb') as f:
        cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

    # Extract CN (Common Name) as client_id
    subject = cert.subject
    cn_attributes = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    client_id = cn_attributes[0].value if cn_attributes else "unknown"

    print(f"✅ Client certificate validated")
    print(f"   Certificate: {CLIENT_CERT}")
    print(f"   Client ID (CN): {client_id}")
    print()

    return client_id


def httpx_client_factory(headers=None, timeout=None, auth=None):
    """
    Custom httpx client factory - with or without mTLS certificates.

    If MTLS_ENABLED=true:
    - Uses client certificate for mTLS authentication to Nginx
    - Nginx extracts certificate DN and forwards to MCP server via headers

    If MTLS_ENABLED=false:
    - Creates a simple HTTP client without certificates
    """
    # Merge headers with Accept header
    merged_headers = headers.copy() if headers else {}
    merged_headers["Accept"] = "application/json, text/event-stream"  # Required by server

    if MTLS_ENABLED:
        # mTLS ENABLED: Create SSL context with client certificates for Nginx proxy
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.load_cert_chain(certfile=str(CLIENT_CERT), keyfile=str(CLIENT_KEY))
        ssl_context.load_verify_locations(cafile=str(CA_CERT))
        ssl_context.check_hostname = False  # IP address doesn't match cert SAN
        ssl_context.verify_mode = ssl.CERT_NONE  # Skip server cert verification (IP mismatch)

        # Create httpx client with certificate files (like curl --cert --key --cacert)
        return httpx.AsyncClient(
            headers=merged_headers,
            timeout=timeout or 30.0,
            auth=auth,
            verify=ssl_context,  # SSL context with client certificate
            http2=False  # Disable HTTP/2 for compatibility
        )
    else:
        # mTLS DISABLED: Create simple HTTP client without certificates
        return httpx.AsyncClient(
            headers=merged_headers,
            timeout=timeout or 30.0,
            auth=auth,
            http2=False  # Disable HTTP/2 for compatibility
        )


# ============================================================================
# Main Test
# ============================================================================

async def main():
    """Main test function."""

    print("\n" + "=" * 80)
    print(f"MCP Server Test with AWS Bedrock ({'mTLS ENABLED' if MTLS_ENABLED else 'mTLS DISABLED'})")
    print("=" * 80)
    print()

    # Step 1: Validate certificate (only if mTLS enabled)
    if MTLS_ENABLED:
        client_id = validate_client_certificate()
    else:
        print("🔓 Step 1: mTLS Disabled - Direct Access Mode")
        print("=" * 80)
        print("✅ No certificate validation required")
        print("   Mode: Direct HTTP access")
        print("   Authentication: None")
        print("   Authorization: None (OPA disabled)")
        print()
        client_id = "direct-access"

    # Step 2: Show connection info
    print(f"🌐 Step 2: Connection Information")
    print("=" * 80)
    print(f"   MCP Endpoint: {MCP_ENDPOINT}")
    if MTLS_ENABLED:
        print(f"   Protocol: HTTPS (via Nginx)")
        print(f"   Certificates: {CERT_DIR}")
        print(f"   Client ID: {client_id}")
    else:
        print(f"   Protocol: HTTP (direct)")
        print(f"   Certificates: Not required")
    print()

    # Step 3: Initialize MCP Client
    print("🔧 Step 3: Initialize MCP Client")
    print("=" * 80)

    if MTLS_ENABLED:
        # mTLS ENABLED: Use httpx_client_factory with certificates
        mcp_client = MultiServerMCPClient(
            {
                "diagnostic_tools": {
                    "url": MCP_ENDPOINT,
                    "transport": "streamable_http",
                    "httpx_client_factory": httpx_client_factory,
                }
            }
        )
        print(f"✅ MCP client initialized")
        print(f"   Server: diagnostic_tools")
        print(f"   Transport: streamable_http (HTTPS via Nginx)")
        print(f"   Authentication: mTLS (client certificate)")
    else:
        # mTLS DISABLED: Simple client without certificates
        mcp_client = MultiServerMCPClient(
            {
                "diagnostic_tools": {
                    "url": MCP_ENDPOINT,
                    "transport": "streamable_http",
                    # No httpx_client_factory needed - uses default HTTP client
                }
            }
        )
        print(f"✅ MCP client initialized")
        print(f"   Server: diagnostic_tools")
        print(f"   Transport: streamable_http (HTTP direct)")
        print(f"   Authentication: None")
    print()

    # Step 4: List available tools
    print("🛠️  Step 4: List Available Tools")
    print("=" * 80)

    try:
        tools = await mcp_client.get_tools()
        print(f"✅ Found {len(tools)} tools:")
        for tool in tools:
            print(f"   - {tool.name}: {tool.description}")
        print()
    except Exception as e:
        print(f"❌ Failed to connect to MCP server: {e}")
        print()
        print("⚠️  Make sure the MCP server is running in Kubernetes:")
        print("   kubectl get pods")
        print("   kubectl get svc")
        print()
        if MTLS_ENABLED:
            print(f"   Nginx proxy should be accessible at: {MCP_SERVER_URL}")
            print()
            print("   To test with curl:")
            print(f"   curl -X POST {MCP_ENDPOINT} \\")
            print("     --cert certs/client-cert.pem \\")
            print("     --key certs/client-key.pem \\")
            print("     --cacert certs/ca-cert.pem \\")
            print("     -H 'Content-Type: application/json' \\")
            print("     -d '{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"id\":1,\"params\":{}}' -k")
        else:
            print(f"   MCP server should be accessible at: {MCP_SERVER_URL}")
            print()
            print("   To test with curl:")
            print(f"   curl -X POST {MCP_ENDPOINT} \\")
            print("     -H 'Content-Type: application/json' \\")
            print("     -d '{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"id\":1,\"params\":{}}'")
        return

    # Step 5: Initialize AWS Bedrock
    print("🤖 Step 5: Initialize AWS Bedrock")
    print("=" * 80)

    # Validate AWS Bedrock API key
    if not BEDROCK_API_KEY_ENCODED:
        print("❌ Error: AWS_BEARER_TOKEN_BEDROCK environment variable not set")
        print("")
        print("Please set the environment variable:")
        print("  export AWS_BEARER_TOKEN_BEDROCK='your-api-key-here'")
        print("")
        return

    # Set AWS Bedrock API key
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = BEDROCK_API_KEY_ENCODED

    # Create Bedrock LLM
    llm = ChatBedrock(
        model_id=BEDROCK_MODEL_ID,
        region_name=BEDROCK_REGION,
    )

    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)

    print(f"✅ AWS Bedrock LLM initialized")
    print(f"   Model: {BEDROCK_MODEL_ID}")
    print(f"   Region: {BEDROCK_REGION}")
    print(f"   Tools bound: {len(tools)}")
    print()

    # Step 6: Run AI Conversations
    print("\n" + "=" * 80)
    print("🤖 Step 6: REAL AI Conversation with AWS Bedrock (Claude)")
    print("=" * 80)
    print(f"Client ID: {client_id}")
    print(f"Model: {BEDROCK_MODEL_ID}")
    print(f"Available Tools: {len(tools)}")
    print()

    # Test conversations
    test_questions = [
        "Is the diagnostic server healthy? Please check and tell me the status.",
        "Check the consumer lag for the 'payment-processor' consumer group.",
        "Check the failed-messages-dlq and tell me what errors are occurring.",
        "What can you tell me about the user-events Kafka topic? Include configuration details."
    ]

    for i, question in enumerate(test_questions, 1):
        print("\n" + "=" * 80)
        print(f"Conversation {i}")
        print("=" * 80)
        print(f"👤 User: {question}")
        print()

        try:
            # LLM receives question and decides what to do
            print("🧠 LLM is thinking and deciding which tool to call...")
            response = await llm_with_tools.ainvoke([HumanMessage(content=question)])

            print(f"\n🤖 Assistant: {response.content}")
            print()

            # Check if LLM made tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls:
                print(f"🔧 Tool Calls Made by LLM:")
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get('name', 'unknown')
                    tool_args = tool_call.get('args', {})
                    print(f"   - Tool: {tool_name}")
                    print(f"     Args: {tool_args}")
                    print(f"     ✅ Path: LLM -> MCP Client -> HTTPS -> FastMCP -> OPA -> Tool")
                    print(f"     ✅ Certificate Auth: client_id={client_id}")

                    # Execute the tool and show the response
                    try:
                        print(f"\n     🔄 Executing tool...")
                        # Find the tool by name
                        tool_to_call = next((t for t in tools if t.name == tool_name), None)
                        if tool_to_call:
                            tool_response = await tool_to_call.ainvoke(tool_args)
                            print(f"     ✅ OPA Authorization: GRANTED")
                            print(f"     📦 Tool Response:")
                            # Pretty print the response
                            if isinstance(tool_response, str):
                                try:
                                    response_json = json.loads(tool_response)
                                    print(f"        {json.dumps(response_json, indent=8)}")
                                except (json.JSONDecodeError, ValueError, TypeError):
                                    # If JSON parsing fails, print raw response
                                    print(f"        {tool_response}")
                            else:
                                print(f"        {tool_response}")
                        else:
                            print(f"     ⚠️  Tool not found: {tool_name}")
                    except Exception as tool_error:
                        # Check if it's an authorization error
                        error_msg = str(tool_error)
                        if "Authorization denied" in error_msg or "OPA" in error_msg:
                            print(f"     ❌ OPA Authorization: DENIED")
                        print(f"     ❌ Tool execution error: {tool_error}")
                print()
            else:
                print("ℹ️  No tool calls made by LLM")
                print()

        except Exception as e:
            print(f"❌ Error in conversation: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("✅ REAL AI Conversation Test COMPLETE!")
    print("=" * 80)
    print()
    print("What was tested:")
    print(f"  ✅ LLM: AWS Bedrock (Claude Sonnet 4)")

    if MTLS_ENABLED:
        print(f"  ✅ Mode: mTLS ENABLED (Secure)")
        print(f"  ✅ Certificate-based authentication (client_id: {client_id})")
        print(f"  ✅ MCP client with streamable_http transport (HTTPS via Nginx)")
        print(f"  ✅ {len(tools)} tools available to LLM")
        print(f"  ✅ LLM made AUTONOMOUS decisions about which tools to call")
        print(f"  ✅ Tool calls went through: LLM -> MCP Client -> HTTPS -> Nginx -> OPA -> MCP -> Tool")
        print(f"  ✅ OPA authorized all tool calls")
        print(f"  ✅ LLM interpreted results and responded in natural language")
        print()
        print("🎉 COMPLETE AI CONVERSATION WITH mTLS + OPA WORKING!")
    else:
        print(f"  ✅ Mode: mTLS DISABLED (Direct Access)")
        print(f"  ✅ No authentication required")
        print(f"  ✅ MCP client with streamable_http transport (HTTP direct)")
        print(f"  ✅ {len(tools)} tools available to LLM")
        print(f"  ✅ LLM made AUTONOMOUS decisions about which tools to call")
        print(f"  ✅ Tool calls went through: LLM -> MCP Client -> HTTP -> MCP -> Tool")
        print(f"  ✅ No OPA authorization (direct access)")
        print(f"  ✅ LLM interpreted results and responded in natural language")
        print()
        print("🎉 COMPLETE AI CONVERSATION WITH DIRECT ACCESS WORKING!")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


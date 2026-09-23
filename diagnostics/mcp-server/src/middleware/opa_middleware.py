"""
OPA Authorization Middleware for FastMCP with Direct mTLS
Extracts client_id from TLS certificate and enforces OPA policies
"""

import logging
from typing import Any, Optional, Dict
import httpx
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request

logger = logging.getLogger(__name__)


class OPAAuthorizationError(Exception):
    """Exception raised when OPA denies authorization."""
    def __init__(self, client_id: str, tool: str, message: str = "Authorization denied"):
        self.client_id = client_id
        self.tool = tool
        super().__init__(f"{message}: client_id={client_id}, tool={tool}")


def get_client_id_from_cert() -> Optional[str]:
    """
    Extract client_id from TLS certificate.

    Priority:
    1. Check for X-Client-Cert-CN/DN header (from Nginx proxy)
    2. Try transport.get_extra_info('ssl_object') (direct access to SSL layer)
    3. Try ASGI TLS extension (uvicorn doesn't implement this yet)
    """
    try:
        import inspect
        from starlette.requests import Request

        # Try to find the request object in the call stack
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if 'request' in frame_locals:
                request = frame_locals['request']
                if isinstance(request, Request):
                    # Method 1: Check for Nginx header (when using Nginx proxy)
                    headers = dict(request.headers)

                    # DEBUG: Log all headers
                    logger.info(f"[AUTH] Request headers: {list(headers.keys())}")
                    for key in ['x-client-cert-dn', 'x-client-cert-cn', 'x-client-cert-issuer', 'x-client-cert-verify']:
                        if key in headers:
                            logger.info(f"[AUTH] Found header {key}: {headers[key]}")

                    # Check for X-Client-Cert-CN header from Nginx
                    if 'x-client-cert-cn' in headers:
                        client_cn = headers['x-client-cert-cn']
                        logger.info(f"[AUTH] Extracted client_id from Nginx header: {client_cn}")
                        return client_cn

                    # Check for X-Client-Cert-DN header and extract CN
                    if 'x-client-cert-dn' in headers:
                        dn = headers['x-client-cert-dn']
                        logger.info(f"[AUTH] Found client DN from Nginx: {dn}")
                        # Extract CN from DN (format: "CN=mcp-client,O=...")
                        for part in dn.split(','):
                            if part.strip().startswith('CN='):
                                cn = part.strip()[3:]
                                logger.info(f"[AUTH] Extracted CN from DN: {cn}")
                                return cn

                    # Method 2: Direct transport access (YOUR DISCOVERY!)
                    scope = request.scope
                    if 'transport' in scope:
                        transport = scope['transport']
                        logger.info(f"[AUTH] Found transport in scope: {type(transport)}")
                        try:
                            ssl_object = transport.get_extra_info('ssl_object')
                            if ssl_object:
                                logger.info(f"[AUTH] Found SSL object: {type(ssl_object)}")
                                peer_cert = ssl_object.getpeercert()
                                if peer_cert:
                                    logger.info(f"[AUTH] Got peer certificate: {peer_cert.keys()}")
                                    subject = peer_cert.get('subject')
                                    if subject:
                                        logger.info(f"[AUTH] Certificate subject: {subject}")
                                        # subject is a tuple of tuples: ((('CN', 'mcp-client'),),)
                                        for rdn in subject:
                                            for key, value in rdn:
                                                if key == 'commonName':
                                                    logger.info(f"[AUTH] ✅ Extracted client_id from transport SSL: {value}")
                                                    return value
                        except Exception as e:
                            logger.info(f"[AUTH] Failed to get cert from transport: {e}")

                    # Method 3: ASGI TLS Extension (uvicorn doesn't implement this)
                    if 'extensions' in scope:
                        extensions = scope['extensions']
                        if 'tls' in extensions:
                            tls_info = extensions['tls']
                            logger.info(f"[AUTH] Found ASGI TLS extension: {tls_info.keys()}")
                            if 'client_cert_name' in tls_info:
                                dn = tls_info['client_cert_name']
                                logger.info(f"[AUTH] Extracted client_id from ASGI TLS extension: {dn}")
                                for part in dn.split(','):
                                    if part.strip().startswith('CN='):
                                        cn = part.strip()[3:]
                                        logger.info(f"[AUTH] Extracted CN: {cn}")
                                        return cn

        logger.warning("[AUTH] No client certificate info found")
        return None
    except Exception as e:
        logger.error(f"[AUTH] Error extracting client_id from certificate: {e}")
        return None


class OPAClient:
    """Client for OPA authorization."""

    def __init__(self, opa_url: str = "http://localhost:8181"):
        self.opa_url = opa_url.rstrip("/")
        self.policy_path = "/v1/data/diagnostic_tools/allow"
        logger.info(f"OPA: {self.opa_url}{self.policy_path}")

    async def authorize(self, client_id: str, method: str = None, tool: str = None, arguments: Optional[Dict[str, Any]] = None) -> bool:
        """Check if client is authorized to call method/tool."""
        opa_input = {"input": {"client_id": client_id}}

        if method:
            opa_input["input"]["method"] = method
        if tool:
            opa_input["input"]["tool"] = tool
        if arguments:
            opa_input["input"]["arguments"] = arguments

        url = f"{self.opa_url}{self.policy_path}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=opa_input, timeout=5.0)
                response.raise_for_status()
                result = response.json()
                is_allowed = result.get("result", False)

                log_msg = f"client_id={client_id}"
                if method:
                    log_msg += f", method={method}"
                if tool:
                    log_msg += f", tool={tool}"
                logger.info(f"[OPA] Decision: {'ALLOW' if is_allowed else 'DENY'} for {log_msg}")
                return is_allowed
        except Exception as e:
            logger.error(f"[OPA] Check failed (defaulting to DENY): {e}")
            return False


class OPAAuthorizationMiddleware(Middleware):
    """
    Middleware that enforces OPA authorization for MCP tool calls.

    Uses FastMCP 2.9+ middleware API with on_call_tool hook for semantic
    tool-level authorization and on_message for other MCP protocol messages.
    """

    def __init__(self, opa_url: str = "http://localhost:8181"):
        super().__init__()
        self.opa_client = OPAClient(opa_url)
        logger.info("[AUTH] OPA Authorization Middleware initialized (FastMCP 2.9+ API)")

    def _extract_client_id(self) -> Optional[str]:
        """
        Extract client_id from HTTP headers set by nginx.

        Returns:
            Client ID extracted from certificate CN, or None if not found
        """
        try:
            # Get the HTTP request object using the FastMCP dependency function
            request = get_http_request()

            if request and hasattr(request, 'headers') and request.headers:
                # Check for nginx reverse proxy headers (matching working example)
                client_dn = request.headers.get('x-ssl-client-s-dn')

                if client_dn:
                    logger.info(f"[AUTH] Found client DN from nginx: {client_dn}")

                    # Extract CN from DN string (format: "CN=mcp-client,OU=Development,O=...")
                    # The DN format uses comma-separated components
                    for part in client_dn.split(','):
                        part = part.strip()
                        if part.startswith('CN='):
                            client_id = part[3:]  # Remove "CN=" prefix
                            logger.info(f"[AUTH] Extracted CN from DN: {client_id}")
                            return client_id

                    logger.warning(f"[AUTH] No CN found in client DN: {client_dn}")
                else:
                    logger.warning("[AUTH] No x-ssl-client-s-dn header found from nginx")
                    # DEBUG: Log all available headers
                    logger.info(f"[AUTH] Available headers: {list(request.headers.keys())}")

                # Fallback: Check for X-Client-ID header (manual override for testing)
                client_id = request.headers.get('x-client-id', '')
                if client_id:
                    logger.info(f"[AUTH] Using client_id from X-Client-ID header: {client_id}")
                    return client_id
            else:
                logger.warning("[AUTH] No request object or headers found")

        except Exception as e:
            logger.error(f"[AUTH] Error extracting client_id from headers: {e}")

        return None

    async def on_call_tool(self, context: MiddlewareContext, call_next) -> Any:
        """
        Called when a tool is called. Enforces OPA authorization.

        This hook is specific to tool calls (FastMCP 2.9+ semantic hook).

        Args:
            context: Middleware context containing the message and FastMCP context
            call_next: Function to call the next middleware or handler

        Returns:
            Result from the tool call if authorized

        Raises:
            OPAAuthorizationError: If authorization fails
        """
        # Extract client_id from HTTP headers
        client_id = self._extract_client_id()

        if not client_id:
            client_id = "unknown"
            logger.warning(f"[AUTH] No client_id found - using 'unknown'")

        # Get tool name and arguments from the message
        tool_name = context.message.name
        arguments = context.message.arguments or {}

        logger.info(f"[AUTH] Tool call: tool={tool_name}, client_id={client_id}")

        # Check authorization with OPA
        is_allowed = await self.opa_client.authorize(
            client_id,
            method="tools/call",
            tool=tool_name,
            arguments=arguments
        )

        if not is_allowed:
            logger.warning(f"[OPA] ❌ DENIED: client_id={client_id}, tool={tool_name}")
            raise OPAAuthorizationError(client_id=client_id, tool=tool_name)

        logger.info(f"[OPA] ✅ ALLOWED: client_id={client_id}, tool={tool_name}")

        # If authorized, continue to the next handler
        return await call_next(context)

    async def on_message(self, context: MiddlewareContext, call_next) -> Any:
        """
        Called for every MCP message (initialize, tools/list, etc.).

        This hook handles non-tool messages like initialize, tools/list, etc.
        Tool calls are handled by on_call_tool which is more specific.

        Args:
            context: Middleware context containing the message
            call_next: Function to call the next middleware or handler

        Returns:
            Result from the message handler if authorized

        Raises:
            OPAAuthorizationError: If authorization fails
        """
        # Extract client_id from HTTP headers
        client_id = self._extract_client_id()

        if not client_id:
            client_id = "unknown"
            logger.warning(f"[AUTH] No client_id found - using 'unknown'")

        method = context.method
        logger.info(f"[AUTH] Message received: method={method}, client_id={client_id}")

        # Check authorization with OPA for non-tool methods
        is_allowed = await self.opa_client.authorize(client_id, method=method)

        if not is_allowed:
            logger.warning(f"[OPA] ❌ DENIED: client_id={client_id}, method={method}")
            raise OPAAuthorizationError(client_id=client_id, tool=method)

        logger.info(f"[OPA] ✅ ALLOWED: client_id={client_id}, method={method}")

        # Proceed with the request
        return await call_next(context)


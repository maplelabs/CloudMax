from typing import Union, Optional

from pydantic import BaseModel, Field

from .app_config import ObservabilitySystemUnion, CodeTriagingAgent, ConnectionConfigUnion


class GenericMcpConnectionTestRequest(BaseModel):
    """
    Generic MCP connection test request for any MCP server (observability systems or diagnostic MCP servers).
    This model is used ONLY for testing connections - it doesn't require a name or observability_system identifier.
    """
    enabled: bool = Field(default=True, description="Whether the connection is enabled")
    connection_config: ConnectionConfigUnion = Field(description="Connection configuration with optional mTLS")

    async def validate_connection(self):
        """Validate generic MCP connection"""
        from src.server.utilities.config_validators import validate_mcp_connection
        return await validate_mcp_connection(
            system_name="MCP Server",  # Generic name for test connections
            endpoint_url=self.connection_config.endpoint_url,
            enabled=self.enabled,
            mtls_enabled=self.connection_config.mtls_enabled,
            ca_cert=self.connection_config.ca_cert,
            client_cert=self.connection_config.client_cert,
            client_key=self.connection_config.client_key
        )


# Type aliases for backward compatibility
McpConnectionTestRequest = ObservabilitySystemUnion
CodeTriageConnectionTestRequest = CodeTriagingAgent

# Union type for connection test requests
# The order is critical for proper parsing:
# 1. McpConnectionTestRequest (ObservabilitySystemUnion) - has 'observability_system' field
# 2. GenericMcpConnectionTestRequest - has 'connection_config' field but NO 'base_url' or 'observability_system'
# 3. CodeTriageConnectionTestRequest (CodeTriagingAgent) - has 'base_url' field
#
# Note: We put GenericMcpConnectionTestRequest BEFORE CodeTriageConnectionTestRequest because
# GenericMcpConnectionTestRequest requires 'connection_config' which CodeTriagingAgent doesn't have.
# This way, if 'connection_config' is present, it will match GenericMcpConnectionTestRequest first.
ConnectionTestRequest = Union[
    McpConnectionTestRequest, GenericMcpConnectionTestRequest, CodeTriageConnectionTestRequest]


class ConnectionTestResponse(BaseModel):
    """Response model for connection tests"""
    success: bool = Field(description="Whether the connection test was successful")
    message: str = Field(description="Test result message")
    response_time_ms: Optional[int] = Field(default=None, description="Response time in milliseconds")

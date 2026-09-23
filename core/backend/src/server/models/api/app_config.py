"""
Pydantic models for Application Configuration API endpoints.
"""
import logging
import time
from typing import Optional, List, Literal, Union, Annotated, Dict, Any

import aiohttp
from pydantic import BaseModel, Field, field_validator, Discriminator

from .constants import DEFAULT_SEVERITY, DEFAULT_API_VERSION
from .enums import DeploymentType, LlmProvider, EmbeddingProvider, ConnectionType, ObservabilitySystem, Severity

logger = logging.getLogger(__name__)


# Reusable validator function for endpoint URLs
def sanitize_url(v: str) -> str:
    """Sanitize endpoint URL by stripping whitespace and trailing slashes."""
    if not v:
        return v

    original = v
    sanitized = v.strip().rstrip('/')

    if original != sanitized:
        logger.info(f"URL sanitized: '{original}' -> '{sanitized}'")

    return sanitized


# Reusable validator decorator for endpoint_url fields
def validate_endpoint_url(cls, v: str) -> str:
    """Classmethod wrapper for sanitize_url to use with @field_validator."""
    return sanitize_url(v)


class HttpHeader(BaseModel):
    """HTTP header key-value pair for MCP connections"""
    key: str = Field(description="Header name")
    value: str = Field(description="Header value")


class AlertGroupingConfig(BaseModel):
    """Configuration for alert grouping and correlation"""
    # Worker Schedule Intervals (in seconds)
    batch_grouping_interval_sec: int = Field(
        default=300,
        ge=60,
        description="Interval for batch grouping worker (seconds). Default: 300 (5 minutes)"
    )
    ungrouped_retry_interval_sec: int = Field(
        default=300,
        ge=60,
        description="Interval for ungrouped retry worker (seconds). Default: 300 (5 minutes)"
    )
    group_triage_interval_sec: int = Field(
        default=300,
        ge=60,
        description="Interval for group triage worker (seconds). Default: 300 (5 minutes)"
    )

    # Lookback Windows
    ungrouped_alerts_lookback_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="How far back to look for ungrouped alerts (hours). Default: 24"
    )
    active_groups_lookback_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="How far back to fetch active groups for context (minutes). Default: 30"
    )
    new_group_validation_lookback_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="Lookback window for validating new group creation (minutes). Default: 30"
    )
    standalone_alert_timeout_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="Time to wait before triaging ungrouped alerts as standalone (minutes). Default: 30"
    )

    # Batch Processing Limits
    max_alerts_per_batch: int = Field(
        default=20,
        ge=10,
        le=500,
        description="Maximum alerts to process per batch grouping run. Default: 20"
    )
    max_active_groups_context: int = Field(
        default=20,
        ge=5,
        le=100,
        description="Maximum active groups to fetch for LLM context. Default: 20"
    )
    max_ungrouped_for_validation: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Max ungrouped alerts to check when validating new groups. Default: 50"
    )


class AlertTriageConfig(BaseModel):
    """Configuration for alert triage by severity levels"""
    enabled_severities: List[Severity] = Field(
        default=[DEFAULT_SEVERITY],
        description="List of alert severity levels that should trigger automated triage",
        min_length=1
    )


class AzureChatOpenAIConfig(BaseModel):
    """Azure OpenAI Chat configuration"""
    llm_type: Literal[LlmProvider.AZURE_OPENAI] = Field(default=LlmProvider.AZURE_OPENAI,
                                                        description="LLM type identifier")
    api_key: str = Field(description="Azure OpenAI API key")
    endpoint_url: str = Field(description="Azure OpenAI endpoint URL")
    deployment_name: str = Field(description="Azure OpenAI deployment name")
    api_version: str = Field(default=DEFAULT_API_VERSION, description="Azure OpenAI API version")

    price_usd_per_1k_ip_tokens: float = Field(default=0, ge=0, description="Price in USD per 1000 input tokens")
    price_usd_per_1k_op_tokens: float = Field(default=0, ge=0, description="Price in USD per 1000 output tokens")

    _sanitize_endpoint_url = field_validator('endpoint_url')(classmethod(validate_endpoint_url))

    async def validate_connection(self):
        """Validate Azure OpenAI LLM connection"""
        from .connection_test import ConnectionTestResponse
        start_time = time.time()

        try:
            # Validate required fields
            if not self.api_key or not self.endpoint_url or not self.deployment_name:
                missing_fields = []
                if not self.api_key: missing_fields.append("api_key")
                if not self.endpoint_url: missing_fields.append("endpoint_url")
                if not self.deployment_name: missing_fields.append("deployment_name")

                return ConnectionTestResponse(
                    success=False,
                    message=f"Azure OpenAI LLM missing required fields: {', '.join(missing_fields)}",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            # Test Azure OpenAI API
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json"
            }

            test_url = f"{self.endpoint_url}/openai/deployments/{self.deployment_name}/chat/completions?api-version={self.api_version}"
            test_payload = {
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(test_url, headers=headers, json=test_payload) as response:
                    response_time_ms = int((time.time() - start_time) * 1000)

                    if response.status in [200, 400]:  # 400 is OK for test payload
                        return ConnectionTestResponse(
                            success=True,
                            message="Azure OpenAI LLM connection successful",
                            response_time_ms=response_time_ms
                        )
                    else:
                        return ConnectionTestResponse(
                            success=False,
                            message=f"Azure OpenAI LLM returned status {response.status}",
                            response_time_ms=response_time_ms
                        )

        except Exception as e:
            return ConnectionTestResponse(
                success=False,
                message=f"Azure OpenAI LLM connection failed: {str(e)}",
                response_time_ms=int((time.time() - start_time) * 1000)
            )


class AWSBedrockConfig(BaseModel):
    """AWS Bedrock configuration"""
    llm_type: Literal[LlmProvider.AWS_BEDROCK_CLAUDE] = Field(default=LlmProvider.AWS_BEDROCK_CLAUDE,
                                                              description="LLM type identifier")
    api_key: str = Field(description="AWS API key")
    region: str = Field(description="AWS region")
    model_id: str = Field(description="AWS Bedrock model ID")

    price_usd_per_1k_ip_tokens: float = Field(default=0, ge=0, description="Price in USD per 1000 input tokens")
    price_usd_per_1k_op_tokens: float = Field(default=0, ge=0, description="Price in USD per 1000 output tokens")

    async def validate_connection(self):
        """Validate AWS Bedrock connection using real API call"""
        from src.server.utilities.config_validators import validate_aws_bedrock_connection
        return await validate_aws_bedrock_connection(
            api_key=self.api_key,
            region=self.region,
            model_id=self.model_id
        )


class AzureAnthropicConfig(BaseModel):
    """Azure Anthropic (Claude) configuration - Claude models hosted on Azure AI Foundry"""
    llm_type: Literal[LlmProvider.AZURE_ANTHROPIC] = Field(default=LlmProvider.AZURE_ANTHROPIC,
                                                           description="LLM type identifier")
    endpoint_url: str = Field(
        description="Azure AI Foundry endpoint URL (e.g., 'https://resource.services.ai.azure.com/anthropic/v1/messages')")
    api_key: str = Field(description="Azure API key for Anthropic models")
    model_id: str = Field(description="Model deployment name (e.g., 'claude-haiku-4-5')")

    price_usd_per_1k_ip_tokens: float = Field(default=0, ge=0, description="Price in USD per 1000 input tokens")
    price_usd_per_1k_op_tokens: float = Field(default=0, ge=0, description="Price in USD per 1000 output tokens")

    async def validate_connection(self):
        """Validate Azure Anthropic connection using real API call"""
        from src.server.utilities.config_validators import validate_azure_anthropic_connection
        return await validate_azure_anthropic_connection(
            endpoint_url=self.endpoint_url,
            api_key=self.api_key,
            model_id=self.model_id
        )


# Union type for LLM configurations with discriminator
LlmConfigUnion = Annotated[
    Union[AzureChatOpenAIConfig, AWSBedrockConfig, AzureAnthropicConfig], Discriminator('llm_type')]


class AzureEmbeddingOpenAIConfig(BaseModel):
    """Azure OpenAI Embedding configuration"""
    embedding_type: Literal[EmbeddingProvider.AZURE_OPENAI] = Field(default=EmbeddingProvider.AZURE_OPENAI,
                                                                    description="Embedding type identifier")
    api_key: str = Field(description="Azure OpenAI API key")
    endpoint_url: str = Field(description="Azure OpenAI endpoint URL")
    deployment_name: str = Field(description="Azure OpenAI deployment name")
    api_version: str = Field(default=DEFAULT_API_VERSION, description="Azure OpenAI API version")

    _sanitize_endpoint_url = field_validator('endpoint_url')(classmethod(validate_endpoint_url))

    async def validate_connection(self):
        """Validate Azure OpenAI Embedding connection"""
        from .connection_test import ConnectionTestResponse
        start_time = time.time()

        try:
            # Validate required fields
            if not self.api_key or not self.endpoint_url or not self.deployment_name:
                missing_fields = []
                if not self.api_key: missing_fields.append("api_key")
                if not self.endpoint_url: missing_fields.append("endpoint_url")
                if not self.deployment_name: missing_fields.append("deployment_name")

                return ConnectionTestResponse(
                    success=False,
                    message=f"Azure OpenAI embedding missing required fields: {', '.join(missing_fields)}",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            # Test Azure OpenAI Embedding API
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json"
            }

            test_url = f"{self.endpoint_url}/openai/deployments/{self.deployment_name}/embeddings?api-version={self.api_version}"
            test_payload = {"input": "test"}

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(test_url, headers=headers, json=test_payload) as response:
                    response_time_ms = int((time.time() - start_time) * 1000)

                    if response.status in [200, 400]:  # 400 is OK for test payload
                        return ConnectionTestResponse(
                            success=True,
                            message="Azure OpenAI embedding connection successful",
                            response_time_ms=response_time_ms
                        )
                    else:
                        return ConnectionTestResponse(
                            success=False,
                            message=f"Azure OpenAI embedding returned status {response.status}",
                            response_time_ms=response_time_ms
                        )

        except Exception as e:
            return ConnectionTestResponse(
                success=False,
                message=f"Azure OpenAI embedding connection failed: {str(e)}",
                response_time_ms=int((time.time() - start_time) * 1000)
            )


# Union type for embedding configurations (currently only one option, no discriminator needed)
EmbeddingConfigUnion = AzureEmbeddingOpenAIConfig


class SecondaryLlmConfig(BaseModel):
    """Secondary LLM configuration"""
    same_as_primary: bool = Field(default=True,
                                  description="Whether to use same configuration as primary LLM (stored in database JSONB)")
    llm_config: Optional[Union[AzureChatOpenAIConfig, AWSBedrockConfig]] = Field(default=None,
                                                                                 description="Secondary LLM configuration (required when same_as_primary=False)")


class CustomDeployment(BaseModel):
    """Custom deployment configuration"""
    primary_llm_config: LlmConfigUnion = Field(
        description="Primary LLM configuration for triage and complex operations")
    secondary_llm_config: SecondaryLlmConfig = Field(default_factory=SecondaryLlmConfig,
                                                     description="Secondary LLM configuration for evaluation and RAG")
    embedding_config: EmbeddingConfigUnion = Field(description="Embedding model configuration")


class StreamableHttpConnection(BaseModel):
    """Streamable HTTP connection configuration (for observability systems without mTLS)"""
    connection_type: Literal[ConnectionType.STREAMABLE_HTTP] = Field(default=ConnectionType.STREAMABLE_HTTP,
                                                                     description="Connection type identifier")
    endpoint_url: str = Field(description="MCP endpoint URL")
    http_headers: List[HttpHeader] = Field(default_factory=list, description="Additional HTTP headers")

    # mTLS Configuration
    mtls_enabled: bool = Field(default=False, description="Enable mutual TLS authentication")
    ca_cert: Optional[str] = Field(default=None, description="CA certificate content (PEM format)")
    client_cert: Optional[str] = Field(default=None, description="Client certificate content (PEM format)")
    client_key: Optional[str] = Field(default=None, description="Client private key content (PEM format)")

    _sanitize_endpoint_url = field_validator('endpoint_url')(classmethod(validate_endpoint_url))


class StreamableHttpConnectionWithMtls(BaseModel):
    """Streamable HTTP connection configuration with mTLS support (for diagnostic MCP servers)"""
    connection_type: Literal[ConnectionType.STREAMABLE_HTTP] = Field(default=ConnectionType.STREAMABLE_HTTP,
                                                                     description="Connection type identifier")
    endpoint_url: str = Field(description="MCP endpoint URL")
    http_headers: List[HttpHeader] = Field(default_factory=list, description="Additional HTTP headers")

    # mTLS Configuration
    mtls_enabled: bool = Field(default=False, description="Enable mutual TLS authentication")
    ca_cert: Optional[str] = Field(default=None, description="CA certificate content (PEM format)")
    client_cert: Optional[str] = Field(default=None, description="Client certificate content (PEM format)")
    client_key: Optional[str] = Field(default=None, description="Client private key content (PEM format)")

    _sanitize_endpoint_url = field_validator('endpoint_url')(classmethod(validate_endpoint_url))


# Connection config for observability systems (no mTLS)
ObservabilityConnectionConfig = StreamableHttpConnection

# Connection config for diagnostic MCP servers (with mTLS)
DiagnosticConnectionConfig = StreamableHttpConnectionWithMtls

# Union type for backward compatibility (used in test endpoints)
ConnectionConfigUnion = StreamableHttpConnectionWithMtls


class GrafanaObservabilitySystem(BaseModel):
    """Grafana observability system configuration"""
    observability_system: Literal[ObservabilitySystem.GRAFANA] = Field(default=ObservabilitySystem.GRAFANA,
                                                                       description="Observability system identifier")
    enabled: bool = Field(default=False, description="Whether the connection is enabled")
    connection_config: ObservabilityConnectionConfig = Field(description="Connection configuration (no mTLS)")

    async def validate_connection(self):
        """Validate Grafana MCP connection"""
        from src.server.utilities.config_validators import validate_mcp_connection
        return await validate_mcp_connection(
            system_name="Grafana",
            endpoint_url=self.connection_config.endpoint_url,
            enabled=self.enabled,
            mtls_enabled=False,  # Observability systems don't support mTLS
            ca_cert=None,
            client_cert=None,
            client_key=None
        )


class JaegerObservabilitySystem(BaseModel):
    """Jaeger observability system configuration"""
    observability_system: Literal[ObservabilitySystem.JAEGER] = Field(default=ObservabilitySystem.JAEGER,
                                                                      description="Observability system identifier")
    enabled: bool = Field(default=False, description="Whether the connection is enabled")
    connection_config: ObservabilityConnectionConfig = Field(description="Connection configuration (no mTLS)")

    async def validate_connection(self):
        """Validate Jaeger MCP connection"""
        from src.server.utilities.config_validators import validate_mcp_connection
        return await validate_mcp_connection(
            system_name="Jaeger",
            endpoint_url=self.connection_config.endpoint_url,
            enabled=self.enabled,
            mtls_enabled=False,  # Observability systems don't support mTLS
            ca_cert=None,
            client_cert=None,
            client_key=None
        )


class OpenSearchObservabilitySystem(BaseModel):
    """OpenSearch observability system configuration"""
    observability_system: Literal[ObservabilitySystem.OPENSEARCH] = Field(default=ObservabilitySystem.OPENSEARCH,
                                                                          description="Observability system identifier")
    enabled: bool = Field(default=False, description="Whether the connection is enabled")
    connection_config: ObservabilityConnectionConfig = Field(description="Connection configuration (no mTLS)")

    async def validate_connection(self):
        """Validate OpenSearch MCP connection"""
        from src.server.utilities.config_validators import validate_mcp_connection
        return await validate_mcp_connection(
            system_name="OpenSearch",
            endpoint_url=self.connection_config.endpoint_url,
            enabled=self.enabled,
            mtls_enabled=False,  # Observability systems don't support mTLS
            ca_cert=None,
            client_cert=None,
            client_key=None
        )


# Union type for observability systems with discriminator
ObservabilitySystemUnion = Annotated[
    Union[GrafanaObservabilitySystem, JaegerObservabilitySystem, OpenSearchObservabilitySystem],
    Field(discriminator='observability_system')]


class DiagnosticMcpServer(BaseModel):
    """Diagnostic MCP Server configuration (separate from observability systems)"""
    name: str = Field(description="Unique name for this diagnostic MCP server instance")
    enabled: bool = Field(default=False, description="Whether the connection is enabled")
    connection_config: DiagnosticConnectionConfig = Field(description="Connection configuration (with mTLS support)")

    async def validate_connection(self):
        """Validate Diagnostic MCP connection"""
        from src.server.utilities.config_validators import validate_mcp_connection
        return await validate_mcp_connection(
            system_name=f"Diagnostic-{self.name}",
            endpoint_url=self.connection_config.endpoint_url,
            enabled=self.enabled,
            mtls_enabled=self.connection_config.mtls_enabled,
            ca_cert=self.connection_config.ca_cert,
            client_cert=self.connection_config.client_cert,
            client_key=self.connection_config.client_key
        )


class DiagnosticMcpServers(BaseModel):
    """Diagnostic MCP Servers configuration"""
    servers: List[DiagnosticMcpServer] = Field(
        default_factory=list,
        description="List of diagnostic MCP server connections"
    )


class McpConnections(BaseModel):
    """MCP connections configuration"""
    systems: List[ObservabilitySystemUnion] = Field(
        min_length=1,
        default=[],
        description="List of observability system connections (at least one required)"
    )


class CodeTriagingAgent(BaseModel):
    """Code triaging agent configuration"""
    enabled: bool = Field(default=False, description="Whether code triaging agent is enabled")
    base_url: str = Field(default="", description="Base URL for code triaging API (e.g., http://code-triage-agent:8002)")
    timeout_seconds: int = Field(default=180, ge=1, le=300, description="Request timeout in seconds")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum number of retries for failed requests")

    async def validate_connection(self):
        """Validate Code Triaging Agent connection"""
        from .connection_test import ConnectionTestResponse
        start_time = time.time()

        try:
            if not self.enabled:
                return ConnectionTestResponse(
                    success=True,
                    message="Code triaging agent is disabled - skipped",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            if not self.base_url:
                return ConnectionTestResponse(
                    success=False,
                    message="Code triaging agent base_url is required",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

            # Test multiple endpoints with fallback
            headers = {"Content-Type": "application/json"}

            base_url = self.base_url.rstrip("/")
            test_urls = [f"{base_url}/health", f"{base_url}/status", base_url]

            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for idx, test_url in enumerate(test_urls, 1):
                    try:
                        async with session.get(test_url, headers=headers) as response:
                            response_time_ms = int((time.time() - start_time) * 1000)

                            if response.status in [200, 404]:  # 404 is OK, means server is responding
                                return ConnectionTestResponse(
                                    success=True,
                                    message=f"Code triaging agent connection successful (endpoint: {test_url}, status: {response.status})",
                                    response_time_ms=response_time_ms
                                )
                    except Exception as e:
                        continue  # Try next URL

                # If all URLs failed
                return ConnectionTestResponse(
                    success=False,
                    message=f"Code triaging agent is not responding on any endpoint (tested: {', '.join(test_urls)})",
                    response_time_ms=int((time.time() - start_time) * 1000)
                )

        except Exception as e:
            logger.error(f"[CODE_TRIAGE] Connection validation error: {type(e).__name__}: {str(e)}")
            return ConnectionTestResponse(
                success=False,
                message=f"Code triaging agent connection failed: {str(e)}",
                response_time_ms=int((time.time() - start_time) * 1000)
            )


class ConfluenceConfig(BaseModel):
    """Confluence integration configuration"""
    enabled: bool = Field(default=False, description="Enable Confluence integration")
    base_url: Optional[str] = Field(default=None, description="Confluence base URL")
    username: Optional[str] = Field(default=None, description="Confluence username")
    api_token: Optional[str] = Field(default=None, description="Confluence API token")


class ExternalRunbookConfig(BaseModel):
    """External runbook sources configuration"""
    confluence: Optional[ConfluenceConfig] = Field(default=None, description="Confluence configuration")


class SetupConfigRequestOrResponse(BaseModel):
    """Request/Response model for setup configuration"""
    alert_triage_config: AlertTriageConfig = Field(description="Alert triage configuration by severity levels")
    alert_grouping_config: AlertGroupingConfig = Field(
        default_factory=AlertGroupingConfig,
        description="Alert grouping and correlation configuration"
    )
    deployment: DeploymentType = Field(description="Agent deployment type")
    custom_deployment: Optional[CustomDeployment] = Field(default=None, description="Custom deployment configuration")
    mcp_connections: McpConnections = Field(description="MCP connections configuration")
    diagnostic_mcp_servers: DiagnosticMcpServers = Field(
        default_factory=DiagnosticMcpServers,
        description="Diagnostic MCP servers configuration (separate from observability systems)"
    )
    external_runbook_config: Optional[ExternalRunbookConfig] = Field(
        default=None,
        description="External runbook sources configuration (Confluence, etc.)"
    )
    code_triaging_agent: CodeTriagingAgent = Field(description="Code triaging agent configuration")
    chaos_system_enabled: bool = Field(default=False, description="Enable chaos engineering workflow integration")
    orchestrator_agents: int = Field(default=5, ge=1, le=20, description="Number of orchestrator agents")
    automatic_triage: bool = Field(default=True, description="Enable automatic triage")
    alert_grouping_enabled: bool = Field(default=True, description="Enable alert grouping and correlation")
    default_config: bool = Field(default=False, description="Whether this is the default configuration")


# Response Models for API endpoints
class ConfigOperationResponse(BaseModel):
    """Response model for config create/update operations"""
    status: Literal["success", "error"] = Field(description="Operation status")
    message: str = Field(description="Operation message")
    validation_results: Dict[str, Any] = Field(description="Connection validation results")

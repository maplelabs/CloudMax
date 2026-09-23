"""
Enums for API models - provides better type safety and IDE support than string literals.
"""
from enum import Enum


class Status(str, Enum):
    """Status values for various operations"""
    PENDING = "pending"  # Job has not been created yet
    QUEUED = "queued"  # Job has been enqueued and is waiting in the queue to be picked up by a worker
    PROCESSING = "processing"  # Job is currently being executed by a worker
    SUCCESS = "success"  # Job completed successfully
    ERROR = "error"  # Job failed with an error


class FaultLedgerStatus(str, Enum):
    """Fault ledger statuses"""
    STARTED = "started"
    FAILED = "failed"
    COMPLETED = "completed"


class Severity(str, Enum):
    """Alert severity levels"""
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Timeline(str, Enum):
    """Time range filter options"""
    THIRTY_MINS = "30m"
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWENTY_FOUR_HOURS = "24h"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    CUSTOM = "custom"


class PlotType(str, Enum):
    """Chart/plot type options"""
    PIE = "pie"
    LINE = "line"


class Relevancy(str, Enum):
    """Knowledge base relevancy levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DeploymentType(str, Enum):
    """Agent deployment types"""
    CUSTOM = "custom"
    AZURE = "azure"


class LlmProvider(str, Enum):
    """Large Language Model provider types"""
    AZURE_OPENAI = "azure-openai"
    AWS_BEDROCK_CLAUDE = "aws-bedrock-claude"
    AZURE_ANTHROPIC = "azure-anthropic"


class EmbeddingProvider(str, Enum):
    """Embedding model provider types"""
    AZURE_OPENAI = "azure-openai"


class ConnectionType(str, Enum):
    """MCP connection types"""
    STREAMABLE_HTTP = "streamable-http"


class ObservabilitySystem(str, Enum):
    """Observability system types"""
    GRAFANA = "grafana"
    JAEGER = "jaeger"
    OPENSEARCH = "opensearch"
    DIAGNOSTIC = "diagnostic"


class ToolResponseType(str, Enum):
    """Tool response types"""
    TEXT = "text"
    JSON = "json"

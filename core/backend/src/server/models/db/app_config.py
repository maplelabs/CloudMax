"""
Database model for Application Setup/Configuration.
Aligns with API models in backend/src/models/api/app_config.py and the Setup UI.
"""
from sqlalchemy import Column, Integer, Boolean, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

from .base import Base, TimestampMixin
from ..api.constants import DEFAULT_SEVERITY
from ..api.enums import Severity, LlmProvider, EmbeddingProvider


class AppConfig(TimestampMixin, Base):
    """SQLAlchemy model for app_config table (singleton-style configuration)."""
    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Alert triage severity whitelist
    enabled_severities = Column(
        ARRAY(SAEnum(Severity, name="severity_enum", create_type=False)),
        nullable=False,
        default=[DEFAULT_SEVERITY],
        doc="List of Severity enums that should be triaged",
    )

    # Primary LLM configuration
    primary_llm_provider = Column(
        SAEnum(LlmProvider, name="llm_provider_enum"),
        nullable=True,
        doc="Selected primary LLM provider type",
    )
    primary_llm_connection_config = Column(
        JSONB,
        nullable=True,
        doc="JSON config for the selected primary LLM provider (shape depends on provider)",
    )

    # Secondary LLM configuration
    secondary_llm_provider = Column(
        SAEnum(LlmProvider, name="llm_provider_enum", create_type=False),
        nullable=True,
        doc="Selected secondary LLM provider type (NULL means no secondary LLM configured)",
    )
    secondary_llm_connection_config = Column(
        JSONB,
        nullable=True,
        doc="JSON config for the secondary LLM provider (NULL means no secondary LLM configured)",
    )

    # Embedding configuration
    embedding_provider = Column(
        SAEnum(EmbeddingProvider, name="embedding_provider_enum"),
        nullable=True,
        doc="Selected embedding model provider",
    )
    embedding_connection_config = Column(
        JSONB,
        nullable=True,
        doc="JSON config for the embedding provider",
    )

    # MCP connections configuration (observability systems: Grafana, Jaeger, OpenSearch)
    mcp_connections = Column(
        JSONB,
        nullable=True,
        doc="JSON config for MCP/observability system connections",
    )

    # Diagnostic MCP servers configuration (separate from observability systems)
    diagnostic_mcp_servers = Column(
        JSONB,
        nullable=True,
        doc="JSON config for diagnostic MCP server connections",
    )

    # External runbook sources configuration (Confluence, Notion, GitHub Wiki, etc.)
    external_runbook_config = Column(
        JSONB,
        nullable=True,
        doc="JSON config for external runbook sources (Confluence, Notion, GitHub Wiki, etc.)",
    )

    # Code triaging agent configuration
    code_triaging_agent_enabled = Column(Boolean, nullable=False, default=False)
    code_triaging_agent_config = Column(
        JSONB,
        nullable=True,
        doc="JSON config for code triaging agent",
    )

    # Orchestrator agents
    # TODO: Set default to higher once we get a higher token limit
    orchestrator_agents = Column(Integer, nullable=False, default=1)

    # Chaos system configuration
    chaos_system_enabled = Column(Boolean, nullable=False, default=False)

    # Automatic triaging
    automatic_triage = Column(Boolean, nullable=False, default=True)

    # Alert grouping enabled/disabled flag
    alert_grouping_enabled = Column(Boolean, nullable=False, default=True)

    # Alert grouping configuration
    alert_grouping_config = Column(
        JSONB,
        nullable=True,
        doc="JSON config for alert grouping and correlation system",
    )

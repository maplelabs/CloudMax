import logging
from typing import Dict, Any, List

from langchain_core.tools import BaseTool

from src.server.models.api.enums import ObservabilitySystem
from src.triage.agent_tools import parse_relative_time, search_in_knowledge_base
from src.triage.agents.abstract_agent import AbstractAgent
from src.triage.agents.apm_observability import prompts

logger = logging.getLogger(__name__)


class APMObservabilityAgent(AbstractAgent):
    """Application Performance Monitoring Specialist that investigates app-level performance using Grafana, Jaeger, and OpenSearch"""

    def get_supported_observability_systems(self) -> List[ObservabilitySystem]:
        """APM Specialist uses Grafana (metrics), Jaeger (traces), and OpenSearch (logs) for application performance analysis."""
        return [ObservabilitySystem.GRAFANA, ObservabilitySystem.JAEGER, ObservabilitySystem.OPENSEARCH]

    async def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the MCP configuration for APM Specialist.
        Uses Grafana (metrics), Jaeger (traces), and OpenSearch (logs) only.
        Does NOT use diagnostic MCP tools (Kafka, PostgreSQL, Kubernetes).

        Returns:
            Dict[str, Any]: MCP server configuration
        """
        return await self._get_generic_mcp_config()

    def get_tools_needed(self) -> List[BaseTool]:
        """
        Get the non-MCP tools needed by the APM Specialist.
        MCP tools (Grafana, Jaeger, OpenSearch) are loaded separately.

        Returns:
            List[BaseTool]: List of required non-MCP tools
        """
        return [
            parse_relative_time,
            search_in_knowledge_base,
        ]

    def get_prompt(self) -> str:
        """
        Get the appropriate prompt for the given workflow mode.

        Returns:
            str: The prompt for this agent and workflow mode
        """
        return prompts.APM_PROMPT

    def get_agent_name(self) -> str:
        """
        Get the name identifier for this agent.

        Returns:
            str: The agent name
        """
        return "APM_Observability_Agent"

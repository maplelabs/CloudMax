from typing import Dict, Any, List

from langchain_core.tools import BaseTool

from src.server.models.api.enums import ObservabilitySystem
from src.triage.agent_tools import parse_relative_time, search_in_knowledge_base
from src.triage.agents.abstract_agent import AbstractAgent
from src.triage.agents.kubernetes_observability import prompts


class KubernetesObservabilityAgent(AbstractAgent):
    """Kubernetes specialist React Agent with the ability to query observability tools for container orchestration investigations"""

    def get_supported_observability_systems(self) -> List[ObservabilitySystem]:
        """Kubernetes agent needs Grafana for metrics and OpenSearch for logs."""
        return [ObservabilitySystem.GRAFANA, ObservabilitySystem.OPENSEARCH]

    async def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the MCP configuration for Kubernetes Agent.
        Only needs Grafana for Kubernetes metrics.

        Returns:
            Dict[str, Any]: MCP server configuration
        """
        return await self._get_generic_mcp_config()

    def get_tools_needed(self) -> List[BaseTool]:
        """
        Get the tools needed by the Kubernetes Agent.

        Returns:
            List[BaseTool]: List of required tools
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
        return prompts.KUBERNETES_PROMPT

    def get_agent_name(self) -> str:
        """
        Get the name identifier for this agent.

        Returns:
            str: The agent name
        """
        return "Kubernetes_Observability_Agent"

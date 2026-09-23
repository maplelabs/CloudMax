from typing import Dict, Any, List

from langchain_core.tools import BaseTool

from src.server.models.api.enums import ObservabilitySystem
from src.triage.agent_tools import parse_relative_time, search_in_knowledge_base
from src.triage.agents.abstract_agent import AbstractAgent
from src.triage.agents.database_observability import prompts


class DatabaseObservabilityAgent(AbstractAgent):
    """Database specialist React Agent with the ability to query observability tools for database-specific investigations"""

    def get_supported_observability_systems(self) -> List[ObservabilitySystem]:
        """Database agent needs Grafana for metrics and OpenSearch for logs."""
        return [ObservabilitySystem.GRAFANA, ObservabilitySystem.OPENSEARCH]

    async def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the MCP configuration for Database Agent.
        Only needs Grafana for Database metrics.
        Returns:
            Dict[str, Any]: MCP server configuration
        """
        return await self._get_generic_mcp_config()

    def get_tools_needed(self) -> List[BaseTool]:
        """
        Get the tools needed by the Database Agent.

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
        return prompts.DATABASE_PROMPT

    def get_agent_name(self) -> str:
        """
        Get the name identifier for this agent.

        Returns:
            str: The agent name
        """
        return "Database_Observability_Agent"

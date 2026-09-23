from typing import Dict, Any, List

from langchain_core.tools import BaseTool

from src.server.models.api.enums import ObservabilitySystem
from src.triage.agent_tools import parse_relative_time, search_in_knowledge_base
from src.triage.agents.abstract_agent import AbstractAgent
from src.triage.agents.diagnostic_tests import prompts


class DiagnosticTestsAgent(AbstractAgent):
    """Diagnostic specialist agent that provides direct access to infrastructure diagnostic tools"""

    def get_supported_observability_systems(self) -> List[ObservabilitySystem]:
        """Diagnostic agent does NOT use observability systems (Grafana, Jaeger, OpenSearch).
        It only uses diagnostic servers for direct infrastructure access."""
        return []  # No observability systems - only diagnostic tools

    def supports_diagnostic_mcp(self) -> bool:
        """Diagnostic agent ONLY uses diagnostic servers."""
        return True

    async def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the MCP configuration for Diagnostic Agent.
        Only loads diagnostic servers, no observability systems.

        Returns:
            Dict[str, Any]: MCP server configuration with only diagnostic servers
        """
        return await self._get_generic_mcp_config()

    def get_tools_needed(self) -> List[BaseTool]:
        """
        Get the tools needed by the Diagnostic Agent.

        Returns:
            List[BaseTool]: List of required tools
        """
        return [
            parse_relative_time,
            search_in_knowledge_base,
        ]

    def get_prompt(self) -> str:
        """
        Get the appropriate prompt for the Diagnostic Agent.

        Returns:
            str: The prompt for this agent
        """
        return prompts.DIAGNOSTIC_TESTS_AGENT_PROMPT

    def get_agent_name(self) -> str:
        """
        Get the name identifier for this agent.

        Returns:
            str: The agent name
        """
        return "Diagnostic_Tests_Agent"

"""
Abstract base class for all observability agents.
Enforces consistent structure and provides common functionality.
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from src.server.models.api.enums import ObservabilitySystem
from src.server.utilities.llm_manager import get_primary_llm_async, LLMManager
from src.server.utilities.config import load_config_from_db, should_use_database_config
from src.triage.agents.middlewares import ToonFormatterMiddleware

logger = logging.getLogger(__name__)


@wrap_tool_call
async def handle_tool_errors(request, handler):
    """Handle tool execution errors with custom messages."""
    try:
        return await handler(request)
    except Exception as e:
        # Log the error with full stack trace
        logger.error(f"Tool execution error: {str(e)}", exc_info=True)
        # Return a custom error message to the model
        return ToolMessage(
            content=f"Tool error: Please check your input and try again. ({str(e)})",
            tool_call_id=request.tool_call["id"]
        )


class AbstractAgent(ABC):
    """
    Abstract base class for all observability agents.
    Enforces consistent structure and provides common functionality.
    """

    def __init__(self):
        """
        Initialize instance variables.
        Note: Use build() class method for proper async initialization.
        """
        self.llm: Union[ChatOpenAI, ChatBedrockConverse]
        self.tools: List[BaseTool] = list()

    @classmethod
    async def build(cls, **kwargs) -> CompiledStateGraph:
        """
        Builder method to create a StateGraph with async initialization.

        Args:
            **kwargs: Optional configuration parameters for future extensibility

        Returns:
            CompiledStateGraph: Fully initialized agent StateGraph
        """
        instance = cls()
        await instance._async_init(**kwargs)
        return instance._create_state_graph()

    async def _async_init(self, **kwargs):
        """
        Async initialization method.

        Args:
            **kwargs: Optional configuration parameters
        """
        # Initialize Primary LLM for triage operations and the tools it would need
        self.llm = await get_primary_llm_async()

        # Store LLM mode for use in _create_state_graph to apply caching middleware
        config = None
        if should_use_database_config():
            config = await load_config_from_db()

        llm_manager = LLMManager(config=config)
        self.llm_mode = llm_manager.llm_mode

        await self.load_tools()

    async def load_tools(self):
        """
        Load the tools asynchronously.
        Combines agent-specific tools with MCP tools based on agent requirements.
        Tools are sorted deterministically by name for prompt caching effectiveness.
        """
        agent_tools: List[BaseTool] = self.get_tools_needed()
        mcp_tools: List[BaseTool] = await self.get_mcp_tools()
        # Sort tools alphabetically by name for deterministic ordering
        # This ensures consistent cache hits across LLM calls
        self.tools = sorted(agent_tools + mcp_tools, key=lambda t: t.name)


    def get_supported_observability_systems(self) -> List[ObservabilitySystem]:
        """
        Get the list of observability systems this agent supports.
        Override this method in subclasses to specify which systems the agent needs.
        
        Returns:
            List[ObservabilitySystem]: List of supported observability systems
        """
        # Default: support all systems (backward compatibility)
        return list(ObservabilitySystem)

    def supports_diagnostic_mcp(self) -> bool:
        """
        Determines if the agent supports diagnostic MCP servers.

        By default, only DiagnosticMcpAgent has access to diagnostic MCP tools.
        Other agents use observability systems (Grafana, Jaeger, OpenSearch).

        This uses a whitelist approach - only agents in DIAGNOSTIC_MCP_ENABLED_AGENTS
        will have access to diagnostic MCP tools.

        Returns:
            bool: True if agent supports diagnostic MCP servers
        """
        # Whitelist of agents that can use diagnostic MCP tools
        DIAGNOSTIC_MCP_ENABLED_AGENTS = {
            "DiagnosticAgent",  # Only the dedicated diagnostic agent
        }

        # Check if this agent's class name is in the whitelist
        agent_class_name = self.__class__.__name__
        return agent_class_name in DIAGNOSTIC_MCP_ENABLED_AGENTS

    async def _get_generic_mcp_config(self) -> Dict[str, Any]:
        """
        Generic MCP configuration loader that all agents can use.
        Loads enabled MCP connections from database config.
        Now handles observability systems (Grafana, Jaeger, OpenSearch) and
        diagnostic MCP servers separately.

        Returns:
            Dict[str, Any]: MCP server configuration
        """
        from src.server.utilities.config import load_config_from_db
        from src.triage.agent_tools.mcp_tools import (
            get_grafana_mcp_connection,
            get_jaeger_mcp_connection,
            get_opensearch_mcp_connection,
            get_diagnostic_mcp_connections
        )

        config = {}
        db_config = await load_config_from_db()

        if not db_config:
            return config

        # Load observability system MCP connections (Grafana, Jaeger, OpenSearch)
        mcp_data = db_config.get("mcp")
        if mcp_data:
            supported_systems = self.get_supported_observability_systems()
            supported_system_names = {system.value for system in supported_systems}

            if isinstance(mcp_data, dict) and "connections" in mcp_data:
                for system in mcp_data["connections"]:
                    system_name = system.get("system")
                    is_enabled = system.get("enabled", False)

                    if is_enabled and system_name in supported_system_names:
                        logger.info(f"Loading MCP connection for {system_name} (enabled: {is_enabled})")
                        try:
                            if system_name == ObservabilitySystem.GRAFANA.value:
                                config["Grafana"] = await get_grafana_mcp_connection()
                                logger.info(f"Successfully loaded Grafana MCP connection")
                            elif system_name == ObservabilitySystem.JAEGER.value:
                                config["Jaeger"] = await get_jaeger_mcp_connection()
                                logger.info(f"Successfully loaded Jaeger MCP connection")
                            elif system_name == ObservabilitySystem.OPENSEARCH.value:
                                config["OpenSearch"] = await get_opensearch_mcp_connection()
                                logger.info(f"Successfully loaded OpenSearch MCP connection")
                        except Exception as e:
                            logger.error(f"Failed to load {system_name} MCP connection: {e}")
                            raise

        # Load diagnostic MCP servers (separate from observability systems)
        supports_diagnostic = self.supports_diagnostic_mcp()
        agent_class_name = self.__class__.__name__
        logger.info(f"Agent '{agent_class_name}' supports_diagnostic_mcp={supports_diagnostic}")

        if supports_diagnostic:
            diagnostic_data = db_config.get("diagnostic_mcp")
            if diagnostic_data:
                logger.info(f"Loading diagnostic MCP server connections for {agent_class_name}")
                try:
                    diagnostic_connections = await get_diagnostic_mcp_connections()
                    config.update(diagnostic_connections)
                    logger.info(
                        f"Successfully loaded {len(diagnostic_connections)} diagnostic MCP server(s) for {agent_class_name}")
                except Exception as e:
                    logger.error(f"Failed to load diagnostic MCP connections: {e}")
                    raise
        else:
            logger.info(f"Skipping diagnostic MCP servers for {agent_class_name} (not in whitelist)")

        return config

    async def get_mcp_tools(self) -> List[BaseTool]:
        """
        Get MCP tools based on agent requirements.
        Uses the MCP configuration defined by each agent.

        Returns:
            List[BaseTool]: List of MCP tools for this agent
        """
        mcp_config = await self.get_mcp_config()
        if not mcp_config:
            return []

        mcp_client = MultiServerMCPClient(mcp_config)
        tools = await mcp_client.get_tools(namespaced_tools=True)
        filtered_tools = await self._filter_blacklisted_tools(tools)
        return filtered_tools

    @staticmethod
    def get_blacklisted_tools() -> List[str]:
        """
        Get the list of blacklisted MCP tool names for this agent.
        
        Returns:
            List[str]: List of tool names to exclude
        """
        return [
            "OpenSearch__get_shards",
            "Grafana__get_dashboard_by_uid",
            "Grafana__add_activity_to_incident",
            "Grafana__create_incident",
            "Grafana__find_error_pattern_logs",
            "Grafana__generate_deeplink",
            "Grafana__fetch_pyroscope_profile",
            "Grafana__list_oncall_schedules",
            "Grafana__list_oncall_team",
            "Grafana__list_oncall_users",
            "Grafana__list_teams",
            "Grafana__list_users_by_org",
            "Grafana__update_dashboard",
            "Grafana__list_sift_investigations",
            "Grafana__list_pyroscope_profile_types",
            "Grafana__list_pyroscope_label_values",
            "Grafana__list_pyroscope_label_names",
            "Grafana__get_sift_analysis",
            "Grafana__get_oncall_shift",
            "Grafana__get_current_oncall_users",
            "Grafana__get_alert_rule_by_uid",
            "Grafana__find_slow_requests",
            "list_alert_rules",
            "Grafana__get_assertions",
            "Grafana__get_incident",
            "Grafana__get_sift_investigation",
            "Grafana__list_contact_points",
            "Grafana__list_incidents",
            "Grafana__list_oncall_teams",

        ]

    async def _filter_blacklisted_tools(self, tools: List[BaseTool]) -> List[BaseTool]:
        """
        Filter out blacklisted MCP tools based on configuration.
        
        Args:
            tools: List of MCP tools from all servers
            
        Returns:
            List of tools with blacklisted tools removed
        """
        filtered_tools = []
        blacklisted_tools = self.get_blacklisted_tools()
        try:
            for tool in tools:
                if tool.name not in blacklisted_tools:
                    filtered_tools.append(tool)
                else:
                    logger.info(f"Excluding blacklisted toolss: {tool.name} for agent {self.get_agent_name()}")

        except Exception as e:
            print(f"Error filtering blacklisted tools: {e}")
            return tools

        return filtered_tools

    def _get_caching_middleware(self):
        """
        Get the appropriate prompt caching middleware based on LLM provider.

        This method uses the centralized get_prompt_caching_middleware() function
        from llm_manager to maintain DRY principle.

        Returns:
            Caching middleware instance or None if not applicable
        """
        from src.server.utilities.llm_manager import get_prompt_caching_middleware

        llm_mode = getattr(self, 'llm_mode', None)

        if not llm_mode:
            return None

        # Use centralized function - single source of truth
        middleware = get_prompt_caching_middleware(llm_mode)

        if middleware:
            logger.info(f"{self.get_agent_name()}: Retrieved caching middleware for {llm_mode}")

        return middleware

    def _create_state_graph(self) -> CompiledStateGraph:
        """
        Create and return a StateGraph for the agent.

        Returns:
            CompiledStateGraph: The agent's state graph
        """
        system_prompt = self.get_prompt()
        agent_name = self.get_agent_name()

        # Build middleware list with prompt caching support
        middlewares = []

        # Add prompt caching middleware first (applied to all LLM calls)
        caching_middleware = self._get_caching_middleware()
        if caching_middleware:
            middlewares.append(caching_middleware)
            logger.info(f"Creating agent '{agent_name}' with prompt caching enabled")
        else:
            logger.info(f"Creating agent '{agent_name}' without prompt caching")

        # Add ToonFormatter and ToolErrorHandler middlewares
        # Middleware execution order: Caching -> ToonFormatter -> ToolErrorHandler
        toon_middleware = ToonFormatterMiddleware(wrap_in_code_block=True)
        middlewares.extend([toon_middleware, handle_tool_errors])

        agent_graph: CompiledStateGraph[Any, None, Any, Any] = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_prompt,
            name=agent_name,
            middleware=middlewares
        )

        return agent_graph

    @abstractmethod
    async def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the MCP configuration for this agent.
        Each agent defines which MCP servers it needs.

        Returns:
            Dict[str, Any]: MCP server configuration
        """
        pass

    @abstractmethod
    def get_prompt(self) -> str:
        """
        Get the appropriate prompt for the given workflow mode.

        Returns:
            str: The prompt for this agent and workflow mode
        """
        pass

    @abstractmethod
    def get_tools_needed(self) -> List[BaseTool]:
        """
        Get the tools needed by this agent.
        Each agent defines which tools it requires.

        Returns:
            List[BaseTool]: List of tools needed by this agent
        """
        pass

    @abstractmethod
    def get_agent_name(self) -> str:
        """
        Get the name identifier for this agent.

        Returns:
            str: The agent name
        """
        pass

"""
Orchestrator workflow implementations using LangGraph Supervisor functionality.
Provides both generic orchestrator (with ObservabilityConciergeAgent) and
agent-specific orchestrator workflows.

The orchestrator uses explicit handoff tools for better agent selection and
triage journey tracking. Each agent has a dedicated handoff tool with clear
descriptions to guide the LLM in making optimal routing decisions.
"""
import logging
from typing import Any, Dict, List
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.graph import StateGraph
from langgraph_supervisor import create_supervisor
from langgraph_supervisor.handoff import create_handoff_tool

from src.server.utilities.config import has_enabled_diagnostic_mcp_servers
from src.server.utilities.llm_manager import get_primary_llm_async
from src.server.utilities.code_triage_config import get_code_triage_config
from src.triage.agent_tools import search_in_knowledge_base, parse_relative_time
from src.triage.agents import (KafkaObservabilityAgent, KubernetesObservabilityAgent, APMObservabilityAgent,
                               DatabaseObservabilityAgent, DiagnosticTestsAgent, CodeTriageAgent)
from src.triage.workflows.prompts import ORCHESTRATOR_PROMPT

# Set up logger
logger = logging.getLogger(__name__)


class HandoffDebugCallback(BaseCallbackHandler):
    """Callback handler to debug handoff tool invocations."""

    def on_tool_start(
            self,
            serialized: Dict[str, Any],
            input_str: str,
            *,
            run_id: UUID,
            parent_run_id: UUID | None = None,
            tags: List[str] | None = None,
            metadata: Dict[str, Any] | None = None,
            **kwargs: Any,
    ) -> Any:
        """Run when tool starts running."""
        pass

    def on_tool_end(
            self,
            output: str,
            *,
            run_id: UUID,
            parent_run_id: UUID | None = None,
            **kwargs: Any,
    ) -> Any:
        """Run when tool ends running."""
        # We can add logging here if needed
        pass


class OrchestratorWorkflow:
    """
    Agent-specific orchestrator workflow using specialized agents.
    The orchestrator routes tasks to appropriate specialist agents based on domain
    using explicit handoff tools for better transparency and control.
    """

    @classmethod
    async def build(cls, **kwargs) -> StateGraph:
        """
        Builder method to create an Agent-Specific Orchestrator StateGraph with async initialization.

        Args:
            **kwargs: Optional configuration parameters

        Returns:
            StateGraph: Fully initialized agent-specific orchestrator StateGraph
        """
        instance = cls()
        orchestrator_graph = await instance._async_init(**kwargs)
        return orchestrator_graph

    @staticmethod
    async def _async_init(**kwargs) -> StateGraph:
        """
        Async initialization method to set up all specialist agents and create orchestrator.

        Args:
            **kwargs: Optional configuration parameters
        """
        # Check if diagnostic MCP servers are enabled before building diagnostic agent
        diagnostic_enabled = await has_enabled_diagnostic_mcp_servers()

        # Initialize all specialist agents in orchestrator mode
        kafka_observability_agent = await KafkaObservabilityAgent.build(workflow_mode="orchestrator")
        kubernetes_observability_agent = await KubernetesObservabilityAgent.build(workflow_mode="orchestrator")
        apm_observability_agent = await APMObservabilityAgent.build(workflow_mode="orchestrator")
        db_observability_agent = await DatabaseObservabilityAgent.build(workflow_mode="orchestrator")

        # Conditionally initialize diagnostic agent only if diagnostic MCP servers are enabled
        diagnostic_agent = None
        if diagnostic_enabled:
            logger.info("Diagnostic MCP servers enabled. Including Diagnostic_Tests_Agent in orchestrator.")
            diagnostic_agent = await DiagnosticTestsAgent.build(workflow_mode="orchestrator")
        else:
            logger.warning("No enabled diagnostic MCP servers found. Excluding Diagnostic_Tests_Agent from orchestrator.")

        # Check if code-triage is enabled and initialize if so
        logger.info("🔍 Checking if Code Triage Agent is enabled...")
        code_triage_config = await get_code_triage_config()
        code_triage_agent = None

        if code_triage_config and code_triage_config.enabled:
            logger.info(f" Code Triage Agent is ENABLED (base_url: {code_triage_config.base_url})")
            try:
                code_triage_agent = await CodeTriageAgent.build(workflow_mode="orchestrator")
                logger.info("Code Triage Agent successfully initialized and ready!")
            except Exception as e:
                logger.error(f"Failed to initialize Code Triage Agent: {e}")
                logger.warning("Continuing without Code Triage Agent")
        else:
            logger.info("Code Triage Agent is DISABLED or not configured")

        # Create explicit handoff tools for agent routing
        # IMPORTANT: agent_name must EXACTLY match the agent's get_agent_name() return value
        handoff_tools = [
            create_handoff_tool(
                agent_name="APM_Observability_Agent",
                description=(
                    "Specializes in application-level performance analysis: service metrics, traces, logs, "
                    "application errors, and application resource usage (memory, CPU within the application process)."
                ),
                add_handoff_messages=True
            ),
            create_handoff_tool(
                agent_name="Kafka_Observability_Agent",
                description=(
                    "Specializes in Kafka message broker analysis: consumer/producer metrics, topics, "
                    "partitions, broker health, and message processing."
                ),
                add_handoff_messages=True
            ),
            create_handoff_tool(
                agent_name="Kubernetes_Observability_Agent",
                description=(
                    "Specializes in Kubernetes infrastructure analysis: pod/container lifecycle, "
                    "node health, cluster resources, and orchestration-layer issues."
                ),
                add_handoff_messages=True
            ),
            create_handoff_tool(
                agent_name="Database_Observability_Agent",
                description=(
                    "Specializes in database performance analysis: connections, queries, transactions, "
                    "locks, and database-level resource usage."
                ),
                add_handoff_messages=True
            )
        ]

        # Conditionally add diagnostic agent handoff tool only if enabled
        if diagnostic_enabled:
            handoff_tools.append(
                create_handoff_tool(
                    agent_name="Diagnostic_Tests_Agent",
                    description="Specializes in performing real-time diagnostic tests to fetch current state of infrastructure and services. The available tools can vary based on the infrastructure and services available.",
                    add_handoff_messages=True
                )
            )

        # Add code-triage handoff tool if enabled
        if code_triage_agent:
            handoff_tools.append(
                create_handoff_tool(
                    agent_name="Code_Triage_Agent",
                    description=(
                        "Specializes in analyzing application code to identify root causes of errors. "
                        "Uses GitHub repository information from runbooks to fetch and analyze code. "
                        "When repository information is available and the alert appears code-related "
                        "(for example exceptions, stack traces, or file-and-line references), you should "
                        "call this agent at least once after infrastructure agents have gathered evidence "
                        "to validate and enrich your root cause analysis."
                    ),
                    add_handoff_messages=True
                )
            )

        # Orchestrator's own tools (not handoff tools)
        orchestrator_tools = [
            search_in_knowledge_base,
            parse_relative_time
        ]

        # Combine orchestrator tools with handoff tools
        # Sort tools alphabetically by name for deterministic ordering
        # This ensures consistent cache hits across LLM calls
        all_tools = sorted(orchestrator_tools + handoff_tools, key=lambda t: t.name)
        logger.info(f"ALL THE TOOLS AVAILABLE FOR ORCHESTRATOR ARE {all_tools}")

        # Build agents list - conditionally include diagnostic and code-triage agents if enabled
        agents_list = [
            kafka_observability_agent,
            kubernetes_observability_agent,
            apm_observability_agent,
            db_observability_agent,
        ]

        if diagnostic_enabled and diagnostic_agent:
            agents_list.append(diagnostic_agent)
            logger.info(f"Orchestrator agents list includes Diagnostic_Tests_Agent")

        # Add code-triage agent if enabled
        if code_triage_agent:
            agents_list.append(code_triage_agent)
            logger.info("Code Triage Agent added to orchestrator agents list")

        logger.info(f"Orchestrator agents list includes {len(agents_list)} total agents")

        # Create the orchestrator using LangGraph Supervisor with explicit handoff tools
        # Note: Orchestrator uses create_supervisor which doesn't support middleware parameter
        # Prompt caching is applied at the specialist agent level instead
        orchestrator_graph = create_supervisor(
            model=await get_primary_llm_async(),
            agents=agents_list,
            tools=all_tools,
            prompt=ORCHESTRATOR_PROMPT,
            supervisor_name="Alert_Triage_Orchestrator",
            add_handoff_messages=True,  # Enable handoff message tracking in conversation history
            parallel_tool_calls=False,  # Disable parallel tool calls for better sequential reasoning
        )

        logger.info("Orchestrator workflow created successfully!")

        return orchestrator_graph
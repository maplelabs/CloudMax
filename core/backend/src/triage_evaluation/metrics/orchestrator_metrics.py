"""
Orchestrator Level Metrics class.
Handles both coordination and task completion metrics for the orchestrator.
"""
import logging
from typing import Dict, Any, List

from deepeval.metrics import MultiTurnMCPUseMetric, MCPTaskCompletionMetric
from deepeval.test_case import ConversationalTestCase, Turn, MCPServer
from mcp.types import Tool

from ..utilities import LangGraphLLMWrapper

logger = logging.getLogger(__name__)


class OrchestratorMetrics:
    """
    Evaluates orchestrator-level metrics: coordination and task completion.
    Collapses sub-agent conversations into MCP tool calls for orchestrator evaluation.
    """

    def __init__(self, llm_wrapper: LangGraphLLMWrapper, alert_name: str, alert_payload: Any):
        """Initialize orchestrator metrics with no thresholds."""
        self.llm_wrapper = llm_wrapper

        # Initialize metrics
        self.coordination_metric = MultiTurnMCPUseMetric(
            model=self.llm_wrapper,
            include_reason=True,
            async_mode=True
        )

        self.task_completion_metric = MCPTaskCompletionMetric(
            model=self.llm_wrapper,
            include_reason=True,
            async_mode=True
        )

        self.alert_context = f"Triage the following:\n\nAlert Name: {alert_name}, Details: {alert_payload}"

    @staticmethod
    async def _get_fake_mcp_servers() -> List[MCPServer]:
        """
        Create MCP servers for orchestrator evaluation.

        Combines delegation tools (dummy) with actual MCP tools from langgraph multi-mcp-server

        Returns:
            List of MCPServer objects with both delegation and real tools
        """
        servers = [
            MCPServer(
                server_name="observability_agents_server",
                available_tools=[
                    Tool(
                        name="delegate_to_kafka_observability_agent",
                        description="Delegates to Kafka agent",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    ),
                    Tool(
                        name="delegate_to_diagnostic_agent",
                        description="Delegates to Diagnostic Agent for real-time infrastructure diagnostics (current Kafka lag, DLQ checks, active DB connections, locks, pod status, events)",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    ),
                    Tool(
                        name="delegate_to_kubernetes_observability_agent",
                        description="Delegates to Kubernetes agent",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    ),
                    Tool(
                        name="delegate_to_apm_observability_agent",
                        description="Delegates to APM agent",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    ),
                    Tool(
                        name="delegate_to_database_observability_agent",
                        description="Delegates to Database agent",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    )
                ]
            ),
            MCPServer(
                server_name="diagnostic_tools_server",
                available_tools=[
                    Tool(
                        name="parse_relative_time",
                        description="Converts relative time expressions to UTC timestamps",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "time_expression": {
                                    "type": "string",
                                    "description": "Relative time expression (e.g., 'now', 'now-1m', 'now-2h')"
                                }
                            },
                            "required": ["time_expression"],
                            "additionalProperties": False
                        }
                    ),
                    Tool(
                        name="search_in_knowledge_base",
                        description="Searches the SRE knowledge base and generates an answer using RAG pipeline",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query for the knowledge base"
                                }
                            },
                            "required": ["query"],
                            "additionalProperties": False
                        }
                    )
                ]
            )
        ]

        return servers

    async def evaluate_agent_utilization(self, turns: List[Turn]) -> Dict[str, Any]:
        """Evaluate coordination capabilities of the orchestrator."""
        logger.info("Evaluating orchestrator coordination with pre-built turns")

        mcp_servers = await self._get_fake_mcp_servers()

        test_case = ConversationalTestCase(
            # Add the human message as the first turn and insert the alert context into it
            turns=[Turn(role="user", content=self.alert_context)] + turns,
            mcp_servers=mcp_servers)

        try:
            await self.coordination_metric.a_measure(test_case)

            # Handle case where score might be None
            metric_score = self.coordination_metric.score if self.coordination_metric.score is not None else 0.0
            score = {
                'score': round(metric_score * 100.0, 0),
                'reason': "\n---\n".join(item[1] for item in self.coordination_metric.tools_scores_reasons_list)
            }
        except Exception as e:
            logger.error(f"Error in coordination metric calculation: {e}")
            # Return a default score for any errors
            score = {
                'score': 0.0,
                'reason': f"Error occurred during coordination evaluation: {str(e)}"
            }

        logger.info(f"Orchestrator coordination evaluation completed with score: {score}")

        return score

    async def evaluate_task_completion(self, turns: List[Turn]) -> Dict[str, Any]:
        """Evaluate task completion given pre-built turns (job provided)."""
        logger.info("Evaluating orchestrator task completion with pre-built turns")

        mcp_servers = await self._get_fake_mcp_servers()

        test_case = ConversationalTestCase(
            # Add the human message as the first turn and insert the alert context into it
            turns=[Turn(role="user", content=self.alert_context)] + turns,
            mcp_servers=mcp_servers
        )

        try:
            await self.task_completion_metric.a_measure(test_case)

            # Handle case where score might be None
            metric_score = self.task_completion_metric.score if self.task_completion_metric.score is not None else 0.0
            score = {
                'score': round(metric_score * 100.0, 0),
                'reason': "\n---\n".join(item[1] for item in self.task_completion_metric.scores_reasons_list)
            }
        except Exception as e:
            logger.error(f"Error in task completion metric calculation: {e}")
            # Return a default score for any errors
            score = {
                'score': 0.0,
                'reason': f"Error occurred during task completion evaluation: {str(e)}"
            }

        logger.info(f"Orchestrator task completion evaluation completed with score: {score}")

        return score

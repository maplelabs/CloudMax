"""
Sub-Agent Level Metrics class.
Handles both tool utilization and task completion metrics for sub-agents.
"""
import logging
from typing import Dict, Any, List, Tuple

from deepeval.metrics import MultiTurnMCPUseMetric, MCPTaskCompletionMetric
from deepeval.test_case import ConversationalTestCase, Turn, MCPServer
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.types import Tool

from src.triage.agents.abstract_agent import AbstractAgent
from ..utilities import LangGraphLLMWrapper

logger = logging.getLogger(__name__)


class SubAgentMetrics:
    """
    Evaluates sub-agent level metrics: tool utilization and task completion.
    Processes each sub-agent invocation separately and averages the results.
    """

    def __init__(self, llm_wrapper: LangGraphLLMWrapper, alert_name: str, alert_payload: Any):
        """Initialize sub-agent metrics with no thresholds."""
        self.llm_wrapper = llm_wrapper
        self.alert_context = f"Alert Name: {alert_name}\nAlert Payload: {alert_payload}"
        self.mcp_servers = None

    async def init_mcp_servers(self):
        self.mcp_servers = await self._get_mcp_servers()

    async def _get_mcp_servers(self) -> List[MCPServer]:
        """
        Create MCP servers for orchestrator evaluation.

        Combines delegation tools (dummy) with actual MCP tools from langgraph multi-mcp-server

        Returns:
            List of MCPServer objects with both delegation and real tools
        """
        servers = [
            MCPServer(
                server_name="observability_tools_server",
                available_tools=await self._fetch_actual_mcp_tools()
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

    @staticmethod
    async def _fetch_actual_mcp_tools() -> List[Tool]:
        """
        Fetch actual MCP tools from langgraph multi-mcp-server for sub-agents.

        Returns:
            List of actual MCP tool names
        """
        from src.triage.agent_tools.mcp_tools import get_grafana_mcp_connection, get_jaeger_mcp_connection
        mcp_client = MultiServerMCPClient(
            {
                "Grafana": await get_grafana_mcp_connection(),
                "Jaeger": await get_jaeger_mcp_connection(),
            }
        )

        tools: List[BaseTool] = await mcp_client.get_tools(namespaced_tools=True)

        blacklisted_tools = set(AbstractAgent.get_blacklisted_tools())

        filtered_tools = []

        for tool in tools:
            if tool.name not in blacklisted_tools:
                filtered_tools.append(Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.args_schema
                ))
            else:
                logger.info(f"Excluding blacklisted tool from evaluation: {tool.name}")

        return filtered_tools

    async def evaluate_tool_utilization(
            self,
            sub_agent_conversations: List[Tuple[str, str, List[Turn]]]
    ) -> Dict[str, Any]:
        """
        Evaluate tool utilization across provided sub-agent conversations.
        """
        # Handle case where there are no sub-agent conversations
        if not sub_agent_conversations:
            logger.info("No sub-agent conversations found for tool utilization evaluation")
            return {
                'score': 0.0,
                'reason': "No sub-agent conversations found to evaluate tool utilization. This may indicate the orchestrator handled the task directly without delegating to sub-agents."
            }

        agents, orchestrator_msg_histories, turns_sets = zip(*sub_agent_conversations)

        logger.info(f"Evaluating sub-agent tool utilization of following agents: {agents}")

        metric_calcs = list()

        for idx, turns_set in enumerate(turns_sets):
            logger.info(f"Evaluating tool utilization for agent {agents[idx]} with {len(turns_set)} turns")

            # Initialize metric
            tool_utilization_metric = MultiTurnMCPUseMetric(
                model=self.llm_wrapper,
                include_reason=True,
                async_mode=True
            )

            agent_context = (f"Given the below context from the orchestrator, provide facts about your domain. "
                             f"Perform tool calls to retrieve data and observability evidence.\n\n"
                             f"CONTEXT:\n{orchestrator_msg_histories[idx]}\n\n"
                             f"ALERT BEING TRIAGED:\n{self.alert_context}")

            # Add the human message as the first turn and insert the alert context into it
            agent_turns = [Turn(role="user", content=agent_context)] + turns_set

            test_case = ConversationalTestCase(turns=agent_turns, mcp_servers=self.mcp_servers)

            try:
                await tool_utilization_metric.a_measure(test_case)
                metric_calcs.append(tool_utilization_metric)
            except Exception as e:
                logger.error(f"Error in sub-agent tool utilization for {agents[idx]}: {e}")
                # Create a dummy metric with score 0 for this agent
                tool_utilization_metric.score = 0.0
                tool_utilization_metric.tools_scores_reasons_list = []
                tool_utilization_metric.args_scores_reasons_list = []
                metric_calcs.append(tool_utilization_metric)

        # Handle case where some metrics might have None scores
        valid_scores = [metric.score for metric in metric_calcs if metric.score is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

        score = {
            'score': round(avg_score * 100.0, 0),
            'reason': "\n\n".join(
                [
                    # Each sub-agent's reasoning is joined into 1 string for overall concatenation
                    "\n---\n".join(
                        item[1]
                        for item in metric.tools_scores_reasons_list + metric.args_scores_reasons_list
                    ) for metric in metric_calcs
                ]
            )
        }

        logger.info(f"Sub-agent tool utilization evaluation completed with score: {score}")

        return score

    async def evaluate_task_completion(
            self,
            sub_agent_conversations: List[Tuple[str, str, List[Turn]]]
    ) -> Dict[str, Any]:
        """
        Evaluate task completion across provided sub-agent conversations (pre-built).
        """
        # Handle case where there are no sub-agent conversations
        if not sub_agent_conversations:
            logger.info("No sub-agent conversations found for task completion evaluation")
            return {
                'score': 0.0,
                'reason': "No sub-agent conversations found to evaluate task completion. This may indicate the orchestrator handled the task directly without delegating to sub-agents."
            }

        agents, orchestrator_msg_histories, turns_sets = zip(*sub_agent_conversations)

        logger.info(f"Evaluating sub-agent tool utilization of following agents: {agents}")

        metric_calcs = list()

        for idx, turns_set in enumerate(turns_sets):
            logger.info(f"Evaluating tool utilization for agent {agents[idx]} with {len(turns_set)} turns")

            # Initialize metric
            task_completion_metric = MCPTaskCompletionMetric(
                model=self.llm_wrapper,
                include_reason=True,
                async_mode=True
            )

            agent_context = (f"Given the below context from the orchestrator, provide facts about your domain. "
                             f"Perform tool calls to retrieve data and observability evidence.\n\n"
                             f"CONTEXT:\n{orchestrator_msg_histories[idx]}\n\n"
                             f"ALERT BEING TRIAGED:\n{self.alert_context}")

            # Add the human message as the first turn and insert the alert context into it
            agent_turns = [Turn(role="user", content=agent_context)] + turns_set

            test_case = ConversationalTestCase(turns=agent_turns, mcp_servers=self.mcp_servers)

            try:
                await task_completion_metric.a_measure(test_case)
                metric_calcs.append(task_completion_metric)
            except Exception as e:
                logger.error(f"Error in sub-agent task completion for {agents[idx]}: {e}")
                # Create a dummy metric with score 0 for this agent
                task_completion_metric.score = 0.0
                task_completion_metric.scores_reasons_list = []
                metric_calcs.append(task_completion_metric)

        # Handle case where some metrics might have None scores
        valid_scores = [metric.score for metric in metric_calcs if metric.score is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

        score = {
            'score': round(avg_score * 100.0, 0),
            'reason': "\n\n".join(
                [
                    # Each sub-agent's reasoning is joined into 1 string for overall concatenation
                    "\n---\n".join(
                        item[1]
                        for item in metric.scores_reasons_list
                    ) for metric in metric_calcs
                ]
            )
        }

        logger.info(f"Sub-agent task completion evaluation completed with score: {score}")

        return score

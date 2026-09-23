"""
ConversationTurnBuilder: Utility to construct DeepEval Turn sequences from
get_formatted_triage_analysis_messages output.

It exposes two views as required:
- get_orchestrator_conversation() -> List[Turn]
- get_sub_agents_conversation() -> List[Tuple[str, List[Turn]]]

Design:
- Single pass preprocessing builds conversation metadata by tracking agent transitions
- Maintains orchestrator conversation state and agent invocation states
- Turn creation follows Requirements.md collapsing strategies
"""
import copy
import json
import logging
import uuid
from collections import OrderedDict
from typing import Dict, List, Tuple, Union, OrderedDict as OrderedDictType, Literal, Optional

from deepeval.test_case import Turn, MCPToolCall
from mcp.types import CallToolResult

from src.server.models.api.alert_traige import TriageAIMessage, TriageToolMessage

logger = logging.getLogger(__name__)


class ConversationTurnBuilder:
    """Builds Turn sequences for orchestrator and sub-agent evaluations."""

    def __init__(
            self,
            messages: List[Union[TriageAIMessage | TriageToolMessage]],
            orchestrator_name: str = "Alert_Triage_Orchestrator".lower()
    ):

        self.messages = messages
        self.orchestrator_name = orchestrator_name

        # Orchestrator conversation indices
        self.orchestrator_msg_indices: List[int] = list()

        # Agent invocations with unique identifiers
        # Key: unique_invocation_id (agent_name__uuid)
        # Value: {"orchestrator_msg_indices": [...], "agent_msg_indices": [...]}
        self.agent_invocations: OrderedDictType[str, Dict[str, List[int]]] = OrderedDict()

        self._build_conversation_metadata()

    def _build_conversation_metadata(self) -> None:
        """
        Build conversation metadata by tracking orchestrator -> agent and vice versa transitions.
        """
        # Which message are we currently at
        mode: Literal["orchestrator", "agent"] = "orchestrator"

        # When we are in agent mode, this points to the current agent invocation i.e., a value in self.agent_invocations
        agent_pointer: Optional[Dict[str, List[int]]] = None

        for i, msg in enumerate(self.messages):

            if i == 0:
                # Handle first message - it could be AI or Tool message
                if self._is_ai_msg(msg):
                    # First message is AI message from orchestrator
                    self.orchestrator_msg_indices.append(i)
                    continue
                elif self._is_tool_msg(msg):
                    # First message is a tool message - determine which agent it belongs to
                    if self._agent(msg) == self.orchestrator_name:
                        self.orchestrator_msg_indices.append(i)
                        continue
                else:
                    # Unknown message type - skip
                    continue

            prev_msg = self.messages[i - 1]

            # No mode change if both messages are from orchestrator or from same agent
            if self._agent(prev_msg) == self._agent(msg):

                if mode == "orchestrator":
                    self.orchestrator_msg_indices.append(i)
                else:
                    agent_pointer["agent_msg_indices"].append(i)

            elif self._agent(msg) == self.orchestrator_name:

                mode = "orchestrator"
                agent_pointer = None

                # Append the last message of agent invocation in orchestrator_msg_indices
                self.orchestrator_msg_indices.append(i - 1)

                self.orchestrator_msg_indices.append(i)

            else:

                mode = "agent"

                agent_pointer = self._create_agent_pointer(self._agent(msg))

                agent_pointer["agent_msg_indices"].append(i)

    def _create_agent_pointer(self, agent_name: str) -> Dict[str, List[int]]:

        unique_invocation_id = f"{agent_name}__{uuid.uuid4()}"

        self.agent_invocations[unique_invocation_id] = {
            "orchestrator_msg_indices": copy.deepcopy(self.orchestrator_msg_indices),
            "agent_msg_indices": list(),
        }

        return self.agent_invocations[unique_invocation_id]

    @staticmethod
    def _is_ai_msg(msg: Union[TriageAIMessage, TriageToolMessage]) -> bool:
        """Check if message is an AI message."""
        return isinstance(msg, TriageAIMessage)

    @staticmethod
    def _is_tool_msg(msg: Union[TriageAIMessage, TriageToolMessage]) -> bool:
        """Check if message is a tool message."""
        return isinstance(msg, TriageToolMessage)

    @staticmethod
    def _agent(msg: Union[TriageAIMessage, TriageToolMessage]) -> str:
        """Get agent name from message."""
        return getattr(msg, "agent_name", "").lower()

    def get_orchestrator_conversation(self) -> List[Turn]:
        """
        Construct orchestrator-focused turns from orchestrator conversation metadata.
        Returns assistant-only turns. Caller can prepend a user alert turn if desired.
        """
        turns: List[Turn] = list()

        for msg_idx in self.orchestrator_msg_indices:

            msg: Union[TriageAIMessage, TriageToolMessage] = self.messages[msg_idx]

            if self._is_tool_msg(msg):

                if len(turns) == 0:
                    # Handle the edge case where the first message is a tool message
                    turns.append(
                        Turn(
                            role="assistant",
                            content="Let me perform some analysis using tools."
                        )
                    )

                if turns[-1].mcp_tools_called is None:
                    turns[-1].mcp_tools_called = list()

                tool_args = dict()
                try:
                    tool_args = json.loads(msg.tool_args)
                except (json.JSONDecodeError, ValueError, TypeError):
                    # If JSON parsing fails, store raw args
                    if msg.tool_args.strip() != "":
                        tool_args = {"raw_args": msg.tool_args}

                # Append tools as MCP tools to the turn as if it was part of the previous turn
                # e.g., AI dictates some content along with set of tool calls
                turns[-1].mcp_tools_called.append(
                    MCPToolCall(
                        name=msg.tool_name,
                        args=tool_args,
                        result=CallToolResult(
                            content=[],
                            structuredContent={"result": msg.tool_response}
                        )
                    )
                )

                # Note: _mcp_interaction is auto-detected by DeepEval based on mcp_tools_called

            elif self._is_ai_msg(msg):

                if self._agent(msg) == self.orchestrator_name:

                    # Orchestrator AI message
                    turns.append(
                        Turn(
                            role="assistant",
                            content=msg.content
                        )
                    )

                else:

                    if turns[-1].mcp_tools_called is None:
                        turns[-1].mcp_tools_called = list()

                    # Delegation message when we're looking the sub-agent's final response
                    # We use MCP tools here as the MCP specific metrics require it in that way
                    turns[-1].mcp_tools_called.append(
                        MCPToolCall(
                            name="delegate_to_{}".format(self._agent(msg)),
                            args=dict(),
                            result=CallToolResult(
                                content=[],
                                structuredContent={"result": msg.content}
                            )
                        )
                    )

                    # Note: _mcp_interaction is auto-detected by DeepEval based on mcp_tools_called

        return turns

    def get_sub_agents_conversations(self) -> List[Tuple[str, str, List[Turn]]]:
        """
        Construct per-invocation sub-agent conversations from agent invocation metadata.
        Returns list of (agent_name, orchestrator_context, turns) for each invocation in chronological order.
        Assistant-only turns; caller can prepend the user alert turn.
        """
        agent_conversations: List[Tuple[str, str, List[Turn]]] = list()

        for agent_invocation_id, agent_invocation_data in self.agent_invocations.items():

            agent_name = agent_invocation_id.split("__")[0]

            orchestrator_msg_indices = agent_invocation_data["orchestrator_msg_indices"]
            agent_msg_indices = agent_invocation_data["agent_msg_indices"]

            orchestrator_msg_history: str = "\n".join([
                json.dumps(self.messages[i].model_dump(exclude={"timestamp"})) for i in orchestrator_msg_indices
            ])

            turns: List[Turn] = list()

            for msg_idx in agent_msg_indices:

                msg: Union[TriageAIMessage, TriageToolMessage] = self.messages[msg_idx]

                # Agent tool message
                if self._is_tool_msg(msg):

                    if len(turns) == 0:
                        # Handle the edge case where the first message is a tool message
                        turns.append(
                            Turn(
                                role="assistant",
                                content="Let me perform some analysis using tools."
                            )
                        )

                    if turns[-1].mcp_tools_called is None:
                        turns[-1].mcp_tools_called = list()

                    tool_args = dict()
                    try:
                        tool_args = json.loads(msg.tool_args)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        # If JSON parsing fails, store raw args
                        if msg.tool_args.strip() != "":
                            tool_args = {
                                "raw_args": msg.tool_args
                            }

                    # Append tools as MCP tools to the turn as if it was part of the previous turn
                    # e.g., AI dictates some content along with set of tool calls
                    turns[-1].mcp_tools_called.append(
                        MCPToolCall(
                            name=msg.tool_name,
                            args=tool_args,
                            result=CallToolResult(
                                content=[],
                                structuredContent={"result": msg.tool_response}
                            )
                        )
                    )

                    # Note: _mcp_interaction is auto-detected by DeepEval based on mcp_tools_called

                else:

                    # Agent AI message
                    turns.append(
                        Turn(
                            role="assistant",
                            content=msg.content
                        )
                    )

            agent_conversations.append((agent_name, orchestrator_msg_history, turns))

        return agent_conversations

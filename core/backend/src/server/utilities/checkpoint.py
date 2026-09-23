"""
Utility functions for working with LangGraph checkpoints and message history.
Adapted from scripts/langgraph_checkpoint_utils.py for use in the backend.
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class CheckpointUtils:
    """Utility class for working with LangGraph checkpoints."""

    def __init__(self, conn_string: Optional[str] = None):
        self.conn_string = conn_string or os.environ.get("POSTGRES_CHECKPOINTER_CONN_STRING")
        if not self.conn_string:
            raise ValueError("PostgreSQL connection string is required")

    async def list_all_threads(self) -> List[str]:
        """List all unique thread IDs in the database."""
        if not self.conn_string:
            raise ValueError("PostgreSQL checkpointer connection string is required")

        thread_ids = set()

        async with AsyncPostgresSaver.from_conn_string(self.conn_string) as checkpointer:
            await checkpointer.setup()

            try:
                # alist is a valid method from AsyncPostgresSaver
                async for checkpoint_tuple in checkpointer.alist({}):
                    thread_id = checkpoint_tuple.config.get("configurable", {}).get("thread_id")
                    if thread_id:
                        thread_ids.add(thread_id)
            except Exception:
                # Silently handle errors during checkpoint iteration (e.g., malformed data, DB connection issues)
                # Return partial results rather than failing the entire operation
                pass

        return sorted(thread_ids)

    async def extract_all_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        """Extract messages from ALL checkpoints of a thread to capture multi-agent interactions."""
        if not self.conn_string:
            raise ValueError("PostgreSQL checkpointer connection string is required")

        async with AsyncPostgresSaver.from_conn_string(self.conn_string) as checkpointer:
            await checkpointer.setup()

            config = {"configurable": {"thread_id": thread_id}}
            all_messages = {}

            # Get all checkpoints and process in chronological order
            # alist is a valid method from AsyncPostgresSaver
            checkpoints = [cp async for cp in checkpointer.alist(config)]  # type: ignore

            for checkpoint_tuple in reversed(checkpoints):
                messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])

                for i, message in enumerate(messages):
                    message_key = self._create_message_key(message, i)

                    if message_key not in all_messages:
                        formatted_msg = self._format_message(message, len(all_messages))
                        if formatted_msg:
                            formatted_msg["checkpoint_step"] = checkpoint_tuple.metadata.get("step", -1)
                            formatted_msg["checkpoint_id"] = checkpoint_tuple.config.get("configurable", {}).get(
                                "checkpoint_id", "")
                            all_messages[message_key] = formatted_msg

            # Sort by index and return
            messages = list(all_messages.values())
            messages.sort(key=lambda x: x["index"])
            return messages

    async def get_triage_analysis_messages(self, thread_id: str) -> Dict[str, Any]:
        """
        Get triage analysis messages formatted for API response.
        
        Args:
            thread_id: Thread ID for the triage analysis
            
        Returns:
            Dict containing formatted messages and metadata
        """
        messages = await self.extract_all_messages(thread_id)

        # Filter and categorize messages
        human_messages = [msg for msg in messages if msg["type"] == "HumanMessage"]
        ai_messages = [msg for msg in messages if msg["type"] == "AIMessage"]
        tool_messages = [msg for msg in messages if msg["type"] == "ToolMessage"]

        # Get the latest AI message as the final analysis
        final_analysis = ai_messages[-1] if ai_messages else None

        return {
            "thread_id": thread_id,
            "total_messages": len(messages),
            "message_counts": {
                "human": len(human_messages),
                "ai": len(ai_messages),
                "tool": len(tool_messages)
            },
            "final_analysis": final_analysis,
            "all_messages": messages,
            "analysis_complete": len(ai_messages) > 0,
            "extracted_at": datetime.now().isoformat()
        }

    # TODO: See if we even need this function
    def _create_message_key(self, message: Any, _: int) -> str:
        """Create a unique key for a message to identify duplicates."""
        if isinstance(message, BaseMessage):
            content = getattr(message, 'content', '')
            msg_type = message.__class__.__name__
            tool_call_id = getattr(message, 'tool_call_id', None)
        elif isinstance(message, dict):
            content = message.get("content", "")
            msg_type = message.get("type", "Unknown")
            tool_call_id = message.get("tool_call_id")
        else:
            return f"unknown:{str(message)}"

        key_parts = [msg_type, str(content)]
        if tool_call_id:
            key_parts.append(f"tool_call_id:{tool_call_id}")

        return "|".join(key_parts)

    def _format_message(self, message: Any, index: int) -> Optional[Dict[str, Any]]:
        """Format a message for API response."""
        if isinstance(message, BaseMessage):
            return self._format_langchain_message(message, index)
        elif isinstance(message, dict):
            return self._format_dict_message(message, index)
        else:
            return {"index": index, "type": "Unknown", "content": str(message), "timestamp": None}

    def _format_langchain_message(self, message: BaseMessage, index: int) -> Dict[str, Any]:
        """Format a LangChain message object."""
        formatted = {
            "index": index,
            "type": message.__class__.__name__,
            "content": getattr(message, 'content', ''),
            "timestamp": getattr(message, 'timestamp', None)
        }

        # Add tool-specific information
        tool_calls = getattr(message, 'tool_calls', None)
        if tool_calls:
            formatted["tool_calls"] = [
                {
                    "name": getattr(tc, 'name', tc.get('name', 'unknown') if hasattr(tc, 'get') else 'unknown'),
                    "args": getattr(tc, 'args', tc.get('args', {}) if hasattr(tc, 'get') else {}),
                    "id": getattr(tc, 'id', tc.get('id', '') if hasattr(tc, 'get') else '')
                }
                for tc in tool_calls
            ]

        tool_call_id = getattr(message, 'tool_call_id', None)
        if tool_call_id:
            formatted["tool_call_id"] = tool_call_id

        name = getattr(message, 'name', None)
        if name:
            formatted["name"] = name

        return formatted

    def _format_dict_message(self, message: dict, index: int) -> Dict[str, Any]:
        """Format a dictionary message."""
        return {
            "index": index,
            "type": message.get("type", "Unknown"),
            "content": message.get("content", ""),
            "timestamp": message.get("timestamp"),
            "tool_calls": message.get("tool_calls"),
            "tool_call_id": message.get("tool_call_id"),
            "name": message.get("name")
        }


# Convenience function for easy import
async def get_triage_analysis_data(thread_id: str, conn_string: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to get triage analysis data from checkpoints.
    
    Args:
        thread_id: Thread ID for the triage analysis
        conn_string: Optional PostgreSQL connection string
        
    Returns:
        Dict containing formatted messages and analysis data
    """
    utils = CheckpointUtils(conn_string)
    return await utils.get_triage_analysis_messages(thread_id)

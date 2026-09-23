"""
TOON Formatter Middleware for Agent Tool Responses.

This middleware converts tool responses to TOON format, reducing token usage
for LLM consumption. TOON (Token-Oriented Object Notation) is a compact format
designed for LLM prompts that typically uses 30-60% fewer tokens than JSON.

Library: Uses python-toon (https://github.com/xaviviro/python-toon)
Spec: https://github.com/toon-format/toon
"""

import json
import logging
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.messages.utils import count_tokens_approximately  # Used in _process_tool_result
from toon import encode as toon_encode

logger = logging.getLogger(__name__)


def _convert_to_toon(content: Any, wrap_in_code_block: bool = True) -> tuple[str, bool]:
    """
    Convert content to TOON format.

    Args:
        content: Content to convert (dict, list, or JSON string)
        wrap_in_code_block: Whether to wrap TOON output in ```toon code blocks

    Returns:
        Tuple of (converted_content, was_converted)
    """
    # Parse content if it's a JSON string
    original_content = content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # Not JSON, use as-is
            return original_content, False

    # Convert to TOON format
    try:
        toon_content = toon_encode(content)
    except Exception as e:
        logger.warning(f"[TOON] Failed to encode content to TOON: {e}")
        # Fall back to JSON if TOON encoding fails
        fallback = json.dumps(content) if isinstance(content, (dict, list)) else str(content)
        return fallback, False

    # Return TOON content with wrapper if requested
    if wrap_in_code_block:
        return f"```toon\n{toon_content}\n```", True
    return toon_content, True


def _process_tool_result(result: Any, tool_name: str, wrap_in_code_block: bool = True,
                         min_savings_percent: float = 5.0) -> Any:
    """
    Process tool result and convert to TOON format if it saves tokens.

    Args:
        result: The tool execution result
        tool_name: Name of the tool that was executed
        wrap_in_code_block: Whether to wrap TOON output in code blocks
        min_savings_percent: Minimum savings percentage to apply TOON (default: 5%)

    Returns:
        Processed result (converted to TOON if applicable)
    """
    if not isinstance(result, ToolMessage):
        return result

    try:
        original_content = result.content

        # Convert tool message content to TOON
        toon_content, was_converted = _convert_to_toon(original_content, wrap_in_code_block)

        if not was_converted:
            return result

        # Calculate savings using token counting
        original_tokens = None
        toon_tokens = None
        try:
            original_tokens = count_tokens_approximately(str(original_content))
            toon_tokens = count_tokens_approximately(toon_content)
            savings = original_tokens - toon_tokens
            savings_percent = (savings / original_tokens * 100) if original_tokens > 0 else 0
        except Exception:
            # Fallback: use character length comparison if token counting fails
            original_tokens = len(str(original_content))
            toon_tokens = len(toon_content)
            savings = original_tokens - toon_tokens
            savings_percent = (savings / original_tokens * 100) if original_tokens > 0 else 0

        # Only use TOON if it saves at least min_savings_percent
        if savings_percent < min_savings_percent:
            logger.debug(
                f"[TOON] Tool response '{tool_name}': "
                f"only {savings_percent:.1f}% savings (threshold: {min_savings_percent}%)"
            )
            return result

        # Create new ToolMessage with TOON content
        new_result = ToolMessage(
            content=toon_content,
            tool_call_id=result.tool_call_id,
            name=result.name if hasattr(result, 'name') else None
        )

        logger.info(
            f"[TOON] Tool response '{tool_name}': "
            f"{original_tokens} → {toon_tokens} tokens "
            f"(saved {savings_percent:.1f}%)"
        )

        return new_result

    except Exception as e:
        logger.warning(
            f"[TOON] Failed to convert tool response to TOON format for '{tool_name}': {e}"
        )
        return result


class ToonFormatterMiddleware(AgentMiddleware):
    """
    Class-based middleware that converts tool responses to TOON format.

    This middleware intercepts tool calls and converts tool response messages
    to TOON format, reducing token usage for LLM consumption.

    TOON (Token-Oriented Object Notation) is a compact format designed for
    LLM prompts that typically uses 30-60% fewer tokens than JSON.

    Usage:
        from src.triage.agents.middlewares import ToonFormatterMiddleware

        agent_graph = create_agent(
            model=llm,
            tools=tools,
            system_prompt=prompt,
            name="agent_name",
            middleware=[ToonFormatterMiddleware()]
        )

    The middleware will automatically:
    - Convert uniform arrays of objects to tabular format
    - Use compact notation for primitive arrays
    - Wrap output in ```toon code blocks for clarity
    - Fall back to original format if conversion fails

    Library: Uses python-toon (https://github.com/xaviviro/python-toon)
    Spec: https://github.com/toon-format/toon
    """

    # Unique identifier for this middleware
    name = "toon_formatter"

    def __init__(self, wrap_in_code_block: bool = True, delimiter: str = ','):
        """
        Initialize the TOON formatter middleware.

        Args:
            wrap_in_code_block: Whether to wrap TOON output in ```toon code blocks
            delimiter: Delimiter to use for arrays (',', '\t', or '|')
        """
        self.wrap_in_code_block = wrap_in_code_block
        self.delimiter = delimiter

    def wrap_tool_call(
            self,
            request: ToolCallRequest,
            handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        """
        Intercept tool call to convert tool response to TOON format (sync version).

        This method executes the tool, then converts the ToolMessage result
        to TOON format before returning it to the agent.

        Args:
            request: The tool call request
            handler: The tool execution handler

        Returns:
            Processed tool result (possibly converted to TOON)
        """
        tool_name = request.tool_call.get('name', 'unknown') if hasattr(request, 'tool_call') else 'unknown'
        logger.debug(f"[TOON] Executing tool (sync): {tool_name}")

        try:
            # Execute the tool
            result = handler(request)
            return _process_tool_result(result, tool_name, self.wrap_in_code_block)
        except Exception as e:
            logger.error(f"[TOON] Error in TOON formatter middleware (sync) for '{tool_name}': {e}")
            # Don't re-raise - let the tool error be handled by other middleware
            return result

    async def awrap_tool_call(
            self,
            request: ToolCallRequest,
            handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage:
        """
        Intercept tool call to convert tool response to TOON format (async version).

        This method executes the tool asynchronously, then converts the ToolMessage result
        to TOON format before returning it to the agent.

        Args:
            request: The tool call request
            handler: The tool execution handler

        Returns:
            Processed tool result (possibly converted to TOON)
        """
        tool_name = request.tool_call.get('name', 'unknown') if hasattr(request, 'tool_call') else 'unknown'
        logger.debug(f"[TOON] Executing tool (async): {tool_name}")

        try:
            # Execute the tool asynchronously
            result = await handler(request)
            return _process_tool_result(result, tool_name, self.wrap_in_code_block)
        except Exception as e:
            logger.error(f"[TOON] Error in TOON formatter middleware (async) for '{tool_name}': {e}")
            # Don't re-raise - let the tool error be handled by other middleware
            return result

"""
Token Counting Middleware and Callback for LLM Calls.

This module provides:
1. GlobalTokenTracker - singleton for aggregating all token usage
2. TokenCountingMiddleware - for agents created with create_agent()
3. TokenCountingCallback - for direct LLM calls (routing LLM)
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class GlobalTokenTracker:
    """
    Singleton class to track token usage across all agents and LLM calls.

    This tracker aggregates token counts from all middleware and callbacks,
    providing a centralized view of token consumption per agent/component.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._counts: Dict[str, Dict[str, int]] = {}
        self._counts_lock = threading.Lock()

    def record_usage(self, agent_name: str, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        """
        Record token usage for a specific agent/component.

        Args:
            agent_name: Name of the agent or component
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            total_tokens: Total tokens
        """
        with self._counts_lock:
            if agent_name not in self._counts:
                self._counts[agent_name] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0,
                }

            self._counts[agent_name]["prompt_tokens"] += prompt_tokens
            self._counts[agent_name]["completion_tokens"] += completion_tokens
            self._counts[agent_name]["total_tokens"] += total_tokens
            self._counts[agent_name]["call_count"] += 1

    def get_counts(self, agent_name: str) -> Dict[str, int]:
        """
        Get token counts for a specific agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Dict with token counts
        """
        with self._counts_lock:
            return self._counts.get(agent_name, {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }).copy()

    def get_all_counts(self) -> Dict[str, Dict[str, int]]:
        """
        Get token counts for all agents.

        Returns:
            Dict mapping agent names to their token counts
        """
        with self._counts_lock:
            return {k: v.copy() for k, v in self._counts.items()}

    def get_grand_total(self) -> Dict[str, int]:
        """
        Get aggregated totals across all agents.

        Returns:
            Dict with total prompt_tokens, completion_tokens, total_tokens, call_count
        """
        with self._counts_lock:
            grand_total = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }
            for counts in self._counts.values():
                grand_total["prompt_tokens"] += counts["prompt_tokens"]
                grand_total["completion_tokens"] += counts["completion_tokens"]
                grand_total["total_tokens"] += counts["total_tokens"]
                grand_total["call_count"] += counts["call_count"]
            return grand_total

    def reset(self):
        """Reset all token counts (call at the start of each workflow)."""
        with self._counts_lock:
            self._counts.clear()


# Global singleton instance
_global_tracker = GlobalTokenTracker()


class TokenCountingMiddleware(AgentMiddleware):
    """
    Middleware that tracks and logs token usage for agent LLM calls.

    This middleware intercepts agent execution to extract and log token usage
    metadata from LLM responses. It tracks:
    - Prompt tokens (input)
    - Completion tokens (output)
    - Total tokens per call
    - Cumulative totals per agent

    Usage:
        from src.agents.middlewares import TokenCountingMiddleware

        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=prompt,
            name="my_agent",
            middleware=[TokenCountingMiddleware(agent_name="my_agent")]
        )

    The middleware will automatically log token usage for each LLM call.
    """

    name = "token_counter"

    def __init__(self, agent_name: str = "unknown_agent"):
        """
        Initialize the token counting middleware.

        Args:
            agent_name: Name of the agent for logging purposes
        """
        self.agent_name = agent_name
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.call_count = 0

    def _extract_token_usage(self, response: Any) -> Optional[Dict[str, int]]:
        """
        Extract token usage from LLM response.

        Args:
            response: LLM response object

        Returns:
            Dict with token counts or None if not available
        """
        usage = None

        # Try different response formats
        if isinstance(response, AIMessage):
            # Check response_metadata for usage info (common in LangChain)
            if hasattr(response, 'response_metadata'):
                metadata = response.response_metadata
                if isinstance(metadata, dict):
                    usage = metadata.get('usage') or metadata.get('token_usage')

            # Check usage_metadata (newer LangChain format)
            if not usage and hasattr(response, 'usage_metadata'):
                um = response.usage_metadata
                if um:
                    usage = {
                        'prompt_tokens': getattr(um, 'input_tokens', 0),
                        'completion_tokens': getattr(um, 'output_tokens', 0),
                        'total_tokens': getattr(um, 'total_tokens', 0)
                    }

        # For dict responses
        elif isinstance(response, dict):
            usage = response.get('usage') or response.get('token_usage')

        return usage

    def _log_token_usage(self, usage: Dict[str, int], context: str = ""):
        """
        Log and accumulate token usage.

        Args:
            usage: Token usage dict
            context: Additional context for logging
        """
        prompt_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
        completion_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
        total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)

        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        self.call_count += 1

        # Report to global tracker
        GlobalTokenTracker().record_usage(
            self.agent_name, prompt_tokens, completion_tokens, total_tokens
        )

        logger.info(
            f"[TOKEN_COUNT] {self.agent_name}{context}: "
            f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens} | "
            f"Cumulative: {self.total_tokens} tokens across {self.call_count} calls"
        )

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Intercept model call to track token usage (sync version).

        Args:
            request: The model call request
            handler: The model execution handler

        Returns:
            Model response with token usage logged
        """
        logger.debug(f"[TOKEN_COUNT] wrap_model_call called for {self.agent_name}")
        try:
            # Execute the model call
            response = handler(request)

            # Extract and log token usage
            usage = self._extract_token_usage(response)
            if usage:
                self._log_token_usage(usage, context=" (sync)")
            else:
                logger.warning(f"[TOKEN_COUNT] No token usage found in response for {self.agent_name}")

            return response

        except Exception as e:
            logger.error(f"[TOKEN_COUNT] Error in token counting middleware: {e}", exc_info=True)
            raise

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Intercept model call to track token usage (async version).

        Args:
            request: The model call request
            handler: The model execution handler

        Returns:
            Model response with token usage logged
        """
        logger.debug(f"[TOKEN_COUNT] awrap_model_call called for {self.agent_name}")
        try:
            # Execute the model call asynchronously
            response = await handler(request)

            # Extract and log token usage
            usage = self._extract_token_usage(response)
            if usage:
                self._log_token_usage(usage, context=" (async)")
            else:
                logger.warning(f"[TOKEN_COUNT] No token usage found in response for {self.agent_name}")

            return response

        except Exception as e:
            logger.error(f"[TOKEN_COUNT] Error in token counting middleware: {e}", exc_info=True)
            raise

class TokenCountingCallback(BaseCallbackHandler):
    """
    Callback handler for tracking token usage in direct LLM calls.

    This is used for the orchestrator's routing LLM which doesn't use create_agent().
    It tracks token usage across all LLM invocations and logs cumulative totals.

    Usage:
        from src.agents.middlewares.token_counter import TokenCountingCallback
        from src.llm_client import get_llm

        callback = TokenCountingCallback(name="routing_llm")
        llm = get_llm()
        response = llm.invoke(messages, config={"callbacks": [callback]})

    The callback will automatically log token usage for each LLM call.
    """

    def __init__(self, name: str = "llm"):
        """
        Initialize the token counting callback.

        Args:
            name: Name for logging purposes
        """
        super().__init__()
        self.name = name
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.call_count = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """
        Called when LLM finishes generating.

        Args:
            response: LLM result containing generations and metadata
            **kwargs: Additional keyword arguments
        """
        try:
            # Extract token usage from llm_output
            if hasattr(response, 'llm_output') and response.llm_output:
                usage = response.llm_output.get('usage') or response.llm_output.get('token_usage')

                if usage:
                    prompt_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                    completion_tokens = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
                    total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)

                    self.total_prompt_tokens += prompt_tokens
                    self.total_completion_tokens += completion_tokens
                    self.total_tokens += total_tokens
                    self.call_count += 1

                    # Report to global tracker
                    GlobalTokenTracker().record_usage(
                        self.name, prompt_tokens, completion_tokens, total_tokens
                    )

                    logger.info(
                        f"[TOKEN_COUNT] {self.name}: "
                        f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens} | "
                        f"Cumulative: {self.total_tokens} tokens across {self.call_count} calls"
                    )

        except Exception as e:
            logger.warning(f"[TOKEN_COUNT] Failed to extract token usage: {e}")

    def get_totals(self) -> Dict[str, int]:
        """
        Get cumulative token usage totals.

        Returns:
            Dict with prompt_tokens, completion_tokens, total_tokens, and call_count
        """
        return {
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
        }

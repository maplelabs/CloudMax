"""
Cache Monitoring Middleware for Prompt Caching.

This module provides middleware to monitor and log prompt caching metrics
for Anthropic and AWS Bedrock LLM calls.
"""

import logging
import threading
from typing import Any, Callable, Dict, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


class GlobalCacheTracker:
    """
    Singleton class to track cache usage across all agents and LLM calls.
    
    This tracker aggregates cache metrics from all middleware,
    providing a centralized view of cache performance.
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
        self._metrics: Dict[str, Dict[str, int]] = {}
        self._metrics_lock = threading.Lock()

    def record_cache_metrics(
        self,
        agent_name: str,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        input_tokens: int = 0
    ):
        """
        Record cache metrics for a specific agent/component.

        Args:
            agent_name: Name of the agent or component
            cache_creation_input_tokens: Tokens used to create cache
            cache_read_input_tokens: Tokens read from cache (cache hits)
            input_tokens: Total input tokens
        """
        with self._metrics_lock:
            if agent_name not in self._metrics:
                self._metrics[agent_name] = {
                    "cache_creation_tokens": 0,
                    "cache_read_tokens": 0,
                    "total_input_tokens": 0,
                    "cache_hit_count": 0,
                    "cache_miss_count": 0,
                    "call_count": 0,
                }

            self._metrics[agent_name]["cache_creation_tokens"] += cache_creation_input_tokens
            self._metrics[agent_name]["cache_read_tokens"] += cache_read_input_tokens
            self._metrics[agent_name]["total_input_tokens"] += input_tokens
            self._metrics[agent_name]["call_count"] += 1
            
            if cache_read_input_tokens > 0:
                self._metrics[agent_name]["cache_hit_count"] += 1
            else:
                self._metrics[agent_name]["cache_miss_count"] += 1

    def get_metrics(self, agent_name: str) -> Dict[str, int]:
        """Get cache metrics for a specific agent."""
        with self._metrics_lock:
            return self._metrics.get(agent_name, {
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
                "total_input_tokens": 0,
                "cache_hit_count": 0,
                "cache_miss_count": 0,
                "call_count": 0,
            }).copy()

    def get_all_metrics(self) -> Dict[str, Dict[str, int]]:
        """Get cache metrics for all agents."""
        with self._metrics_lock:
            return {k: v.copy() for k, v in self._metrics.items()}

    def reset(self):
        """Reset all cache metrics."""
        with self._metrics_lock:
            self._metrics.clear()


class CacheMonitoringMiddleware(AgentMiddleware):
    """
    Middleware that tracks and logs prompt caching metrics for LLM calls.
    
    This middleware extracts cache-related metadata from LLM responses
    to track cache creation, cache hits, and cost savings.
    
    Supports:
    - Anthropic Claude (cache_creation_input_tokens, cache_read_input_tokens)
    - AWS Bedrock (similar structure)
    
    Usage:
        from src.agents.middlewares.cache_monitor import CacheMonitoringMiddleware
        
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=prompt,
            name="my_agent",
            middleware=[
                CacheMonitoringMiddleware(agent_name="my_agent"),
                TokenCountingMiddleware(agent_name="my_agent")
            ]
        )
    """

    name = "cache_monitor"

    def __init__(self, agent_name: str = "unknown_agent"):
        """
        Initialize the cache monitoring middleware.

        Args:
            agent_name: Name of the agent for logging purposes
        """
        self.agent_name = agent_name
        self.total_cache_creation = 0
        self.total_cache_read = 0
        self.total_input_tokens = 0
        self.cache_hit_count = 0
        self.cache_miss_count = 0

    def _extract_cache_metrics(self, response: Any) -> Optional[Dict[str, int]]:
        """
        Extract cache metrics from LLM response.

        Args:
            response: LLM response object (can be AIMessage or ModelResponse)

        Returns:
            Dict with cache metrics or None if not available
        """
        cache_metrics = None

        # Log response type for debugging
        logger.debug(f"[CACHE_DEBUG] Response type: {type(response)}")

        # Handle ModelResponse (from create_agent with structured output)
        # ModelResponse has 'result' and 'structured_response' attributes
        if hasattr(response, 'result'):
            logger.debug(f"[CACHE_DEBUG] ModelResponse detected, checking result attribute")
            result = response.result
            logger.debug(f"[CACHE_DEBUG] Result type: {type(result)}")

            # Result might be an AIMessage or a list containing AIMessage
            if isinstance(result, list):
                logger.debug(f"[CACHE_DEBUG] Result is a list with {len(result)} items")
                for i, item in enumerate(result):
                    logger.debug(f"[CACHE_DEBUG] Item {i} type: {type(item)}")
                    if isinstance(item, AIMessage):
                        logger.debug(f"[CACHE_DEBUG] Found AIMessage in result list at index {i}")
                        cache_metrics = self._extract_from_ai_message(item)
                        if cache_metrics:
                            break
            elif isinstance(result, AIMessage):
                logger.debug(f"[CACHE_DEBUG] Result is directly an AIMessage")
                cache_metrics = self._extract_from_ai_message(result)

        # Try checking messages attribute (older LangChain versions)
        if not cache_metrics and hasattr(response, 'messages') and response.messages:
            logger.debug(f"[CACHE_DEBUG] Checking messages attribute with {len(response.messages)} messages")
            for i, msg in enumerate(response.messages):
                if isinstance(msg, AIMessage):
                    logger.debug(f"[CACHE_DEBUG] Found AIMessage in messages at index {i}")
                    cache_metrics = self._extract_from_ai_message(msg)
                    if cache_metrics:
                        break

        # Direct AIMessage
        if not cache_metrics and isinstance(response, AIMessage):
            logger.debug(f"[CACHE_DEBUG] Direct AIMessage detected")
            cache_metrics = self._extract_from_ai_message(response)

        # Log when we have metrics to help debug
        if cache_metrics:
            logger.debug(f"[CACHE_DEBUG] Extracted metrics: {cache_metrics}")
        else:
            logger.debug(f"[CACHE_DEBUG] No cache metrics found in response")

        return cache_metrics

    def _extract_from_ai_message(self, message: AIMessage) -> Optional[Dict[str, int]]:
        """
        Extract cache metrics from an AIMessage.

        Args:
            message: AIMessage object

        Returns:
            Dict with cache metrics or None if not available
        """
        cache_metrics = None

        # Check usage_metadata (Anthropic/Bedrock format)
        if hasattr(message, 'usage_metadata'):
            um = message.usage_metadata
            logger.debug(f"[CACHE_DEBUG] usage_metadata type: {type(um)}, value: {um}")
            if um:
                # Handle both dict and object formats
                if isinstance(um, dict):
                    # Check for nested input_token_details (newer Anthropic format)
                    input_token_details = um.get('input_token_details', {})

                    cache_metrics = {
                        # Try new format first (cache_read, cache_creation)
                        'cache_creation_input_tokens': (
                            input_token_details.get('cache_creation', 0) or
                            um.get('cache_creation_input_tokens', 0)
                        ),
                        'cache_read_input_tokens': (
                            input_token_details.get('cache_read', 0) or
                            um.get('cache_read_input_tokens', 0)
                        ),
                        'input_tokens': um.get('input_tokens', 0),
                    }
                else:
                    cache_metrics = {
                        'cache_creation_input_tokens': getattr(um, 'cache_creation_input_tokens', 0),
                        'cache_read_input_tokens': getattr(um, 'cache_read_input_tokens', 0),
                        'input_tokens': getattr(um, 'input_tokens', 0),
                    }

                logger.debug(f"[CACHE_DEBUG] Extracted from usage_metadata: {cache_metrics}")

        # Also check response_metadata
        if not cache_metrics and hasattr(message, 'response_metadata'):
            metadata = message.response_metadata
            logger.debug(f"[CACHE_DEBUG] response_metadata: {metadata}")
            if isinstance(metadata, dict) and 'usage' in metadata:
                usage = metadata['usage']
                input_token_details = usage.get('input_token_details', {})

                cache_metrics = {
                    'cache_creation_input_tokens': (
                        input_token_details.get('cache_creation', 0) or
                        usage.get('cache_creation_input_tokens', 0)
                    ),
                    'cache_read_input_tokens': (
                        input_token_details.get('cache_read', 0) or
                        usage.get('cache_read_input_tokens', 0)
                    ),
                    'input_tokens': usage.get('input_tokens', 0) or usage.get('prompt_tokens', 0),
                }

        return cache_metrics

    def _log_cache_metrics(self, metrics: Dict[str, int], context: str = ""):
        """
        Log and accumulate cache metrics.

        Args:
            metrics: Cache metrics dict
            context: Additional context for logging
        """
        cache_creation = metrics.get('cache_creation_input_tokens', 0)
        cache_read = metrics.get('cache_read_input_tokens', 0)
        input_tokens = metrics.get('input_tokens', 0)

        self.total_cache_creation += cache_creation
        self.total_cache_read += cache_read
        self.total_input_tokens += input_tokens

        if cache_read > 0:
            self.cache_hit_count += 1
        else:
            self.cache_miss_count += 1

        # Report to global tracker
        GlobalCacheTracker().record_cache_metrics(
            self.agent_name, cache_creation, cache_read, input_tokens
        )

        # Calculate cache hit rate
        total_calls = self.cache_hit_count + self.cache_miss_count
        hit_rate = (self.cache_hit_count / total_calls * 100) if total_calls > 0 else 0

        # Estimate cost savings (Anthropic pricing: ~$0.30/1M input tokens, ~90% discount for cached)
        # Cache read tokens cost 10% of normal price, so 90% savings
        cost_savings = (cache_read * 0.0000003 * 0.9) if cache_read > 0 else 0

        if cache_read > 0:
            logger.info(
                f"[CACHE_HIT] {self.agent_name}{context}: "
                f"cache_read={cache_read} tokens, cache_creation={cache_creation} tokens | "
                f"Hit rate: {hit_rate:.1f}% ({self.cache_hit_count}/{total_calls} calls) | "
                f"Total cached: {self.total_cache_read} tokens, Savings: ~${cost_savings:.4f}"
            )
        elif cache_creation > 0:
            logger.info(
                f"[CACHE_MISS] {self.agent_name}{context}: "
                f"cache_creation={cache_creation} tokens (new cache entry) | "
                f"Hit rate: {hit_rate:.1f}% ({self.cache_hit_count}/{total_calls} calls)"
            )

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Intercept model call to track cache usage (sync version).

        Args:
            request: The model call request
            handler: The model execution handler

        Returns:
            Model response with cache metrics logged
        """
        logger.debug(f"[CACHE_MONITOR] wrap_model_call invoked for {self.agent_name}")
        try:
            response = handler(request)
            logger.debug(f"[CACHE_MONITOR] Response type: {type(response)}")

            metrics = self._extract_cache_metrics(response)
            if metrics:
                # Always log if we extracted metrics, even if both are 0
                # (helps debug why caching isn't working)
                if (metrics.get('cache_creation_input_tokens', 0) > 0 or
                    metrics.get('cache_read_input_tokens', 0) > 0):
                    self._log_cache_metrics(metrics, context=" (sync)")
                else:
                    # Log a warning if cache metrics exist but are all zero
                    logger.info(f"[CACHE_ZERO] {self.agent_name}: Cache metrics present but both cache_read=0 and cache_creation=0. "
                               f"Prompt caching might not be working correctly.")
            else:
                logger.debug(f"[CACHE_MONITOR] No cache metrics to log for {self.agent_name}")

            return response

        except Exception as e:
            logger.error(f"[CACHE_MONITOR] Error in cache monitoring: {e}", exc_info=True)
            raise

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Intercept model call to track cache usage (async version).

        Args:
            request: The model call request
            handler: The model execution handler

        Returns:
            Model response with cache metrics logged
        """
        logger.debug(f"[CACHE_MONITOR] awrap_model_call invoked for {self.agent_name}")
        try:
            response = await handler(request)
            logger.debug(f"[CACHE_MONITOR] Response type: {type(response)}")

            metrics = self._extract_cache_metrics(response)
            if metrics:
                # Always log if we extracted metrics, even if both are 0
                if (metrics.get('cache_creation_input_tokens', 0) > 0 or
                    metrics.get('cache_read_input_tokens', 0) > 0):
                    self._log_cache_metrics(metrics, context=" (async)")
                else:
                    # Log a warning if cache metrics exist but are all zero
                    logger.info(f"[CACHE_ZERO] {self.agent_name}: Cache metrics present but both cache_read=0 and cache_creation=0. "
                               f"Prompt caching might not be working correctly.")
            else:
                logger.debug(f"[CACHE_MONITOR] No cache metrics to log for {self.agent_name}")

            return response

        except Exception as e:
            logger.error(f"[CACHE_MONITOR] Error in cache monitoring: {e}", exc_info=True)
            raise


"""
Token Rate Limiter - Smart rate limiting with usage metadata and tiktoken fallback
Provides API-style rate limiting for LLM calls with intelligent token calculation.
"""
import logging
import time
from typing import Any, Optional
from uuid import UUID

import tiktoken
from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


class TokenRateLimiter(BaseCallbackHandler):
    """Smart token rate limiter with API-style fixed windows."""

    def __init__(
            self,
            tokens_per_minute: int = 400000,
            check_every_n_seconds: float = 0.25,
            window_type: str = "fixed",
            usage_callback: UsageMetadataCallbackHandler = None

    ) -> None:
        """Initialize the TokenRateLimiter with API-style windowed rate limiting."""
        super().__init__()

        # Rate limiting configuration
        self.tokens_per_minute = tokens_per_minute
        self.check_every_n_seconds = check_every_n_seconds
        self.window_type = window_type

        # Fixed window tracking
        self.minute_window_start = time.time()
        self.tokens_used_this_minute = 0

        # Statistics
        self.total_tokens_consumed = 0
        self.requests_made = 0
        self.rate_limit_hits = 0
        self.total_wait_time = 0.0
        self.usage_callback = usage_callback

        # Cache-aware tracking
        self._pending_estimates = {}  # {run_id: estimated_tokens}
        self.total_cache_read_tokens = 0  # Track cache reads (don't count against limit)
        self.total_cache_write_tokens = 0  # Track cache writes (DO count against limit)

        # Initialize tiktoken encoder
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
            logger.debug(f"TokenRateLimiter: tiktoken encoder loaded successfully")
        except Exception as e:
            logger.warning(f"TokenRateLimiter: Failed to load tiktoken encoder: {e}")
            self.encoder = None

        logger.info(f"TokenRateLimiter: Cache-aware rate limiting configured (limit: {tokens_per_minute} TPM)")

    def count_tokens_with_tiktoken(self, text: str) -> int:
        """Count tokens using tiktoken."""
        if not self.encoder:
            return len(text.split())  # Fallback to word count
        try:
            return len(self.encoder.encode(text))
        except Exception as e:
            logger.warning(f"TokenRateLimiter: tiktoken encoding failed: {e}")
            return len(text.split())

    def on_chat_model_start(
            self,
            serialized: dict[str, Any],
            messages: list[list[BaseMessage]],
            *,
            run_id: UUID,
            parent_run_id: Optional[UUID] = None,
            tags: Optional[list[str]] = None,
            metadata: Optional[dict[str, Any]] = None,
            **kwargs: Any,
    ) -> Any:
        """Run when a chat model starts running."""
        logger.debug(f"Chat model starting (Request #{self.requests_made + 1})")

        all_messages = [msg for batch in messages for msg in batch]
        if not all_messages:
            return

        # Estimate tokens for THIS call by counting all message content
        # NOTE: This is before the LLM call, so we don't know cache_read yet.
        # We estimate conservatively and adjust after with actual cache metrics.
        estimated_tokens = 0

        for msg in all_messages:
            content = str(getattr(msg, "content", msg))
            estimated_tokens += self.count_tokens_with_tiktoken(content)

        # Add overhead for message formatting (typically 10-20% for chat format)
        estimated_tokens = int(estimated_tokens * 1.15)

        # Store run_id for later adjustment when we get actual usage
        self._pending_estimates[run_id] = estimated_tokens

        # Acquire tokens before LLM call (conservative estimate)
        self._acquire(estimated_tokens, blocking=True)

    def on_llm_end(
            self,
            response: Any,
            *,
            run_id: UUID,
            parent_run_id: Optional[UUID] = None,
            **kwargs: Any,
    ) -> Any:
        """
        Run when LLM ends - adjust token count based on actual cache usage.

        NOTE: This adjustment happens AFTER the LLM call completes, so it doesn't
        help the current call (which already happened). However, it's still important
        because:
        1. It prevents over-estimation from accumulating and causing false rate limits
           on subsequent calls within the same minute window
        2. It provides accurate quota usage statistics
        3. It aligns with Anthropic's post-call cache-aware rate limiting model
        """
        # Check if we have usage metadata from the LLM response
        if not self.usage_callback or not self.usage_callback.usage_metadata:
            return

        # Extract cache metrics from usage metadata
        total_cache_read = 0
        total_cache_write = 0
        total_input = 0

        for model_name, llm_usage in self.usage_callback.usage_metadata.items():
            token_details = llm_usage.get("input_token_details", {})
            cache_read = token_details.get("cache_read", 0)
            cache_creation = token_details.get("cache_creation", 0)
            input_tokens = llm_usage.get("input_tokens", 0)

            total_cache_read += cache_read
            total_cache_write += cache_creation
            total_input += input_tokens

        # Track cache stats
        self.total_cache_read_tokens += total_cache_read
        self.total_cache_write_tokens += total_cache_write

        # Get the estimated tokens we used for pre-acquisition
        estimated_tokens = self._pending_estimates.pop(run_id, None)

        if estimated_tokens and total_cache_read > 0:
            # Actual tokens against limit: input_tokens + cache_creation_tokens
            # (cache_read doesn't count per Anthropic spec)
            actual_tokens_against_limit = total_input + total_cache_write

            # Refund the cache_read portion to prevent accumulating over-estimation
            refund = estimated_tokens - actual_tokens_against_limit

            if refund > 0:
                # Adjust minute window usage
                self.tokens_used_this_minute = max(0, self.tokens_used_this_minute - refund)

                # Also adjust total consumed to reflect actual tokens against limit
                self.total_tokens_consumed = max(0, self.total_tokens_consumed - refund)

    def _acquire(self, tokens_needed: int, blocking: bool = True) -> bool:
        """Acquire tokens using API-style fixed windows."""
        current_time = time.time()

        # Check if we need to reset the minute window
        if current_time - self.minute_window_start >= 60.0:
            self.minute_window_start = current_time
            self.tokens_used_this_minute = 0

        logger.debug(f"ACQUIRING: {tokens_needed} tokens")

        # Check if we have enough tokens in current window
        if self.tokens_used_this_minute + tokens_needed <= self.tokens_per_minute:

            # We have enough tokens
            self.tokens_used_this_minute += tokens_needed
            self.total_tokens_consumed += tokens_needed
            self.requests_made += 1

            return True

        else:

            # Not enough tokens - need to wait for next window
            if blocking:

                time_until_reset = 60.0 - (current_time - self.minute_window_start)

                logger.warning(f"RATE LIMITED: Need {tokens_needed} tokens, only "
                               f"{self.tokens_per_minute - self.tokens_used_this_minute} available")
                logger.warning(f"Waiting {time_until_reset:.1f}s until next minute window")

                self.rate_limit_hits += 1
                self.total_wait_time += time_until_reset

                time.sleep(time_until_reset)

                # Reset window and try again
                self.minute_window_start = time.time()
                self.tokens_used_this_minute = 0

                return self._acquire(tokens_needed, blocking=False)

            else:

                return False

    def get_stats(self) -> dict:
        """Get rate limiter statistics including cache-aware metrics."""
        return {
            "total_tokens_consumed": self.total_tokens_consumed,
            "requests_made": self.requests_made,
            "rate_limit_hits": self.rate_limit_hits,
            "total_wait_time": self.total_wait_time,
            "tokens_per_minute": self.tokens_per_minute,
            "current_minute_usage": self.tokens_used_this_minute,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "cache_read_percentage": (
                (self.total_cache_read_tokens / (self.total_tokens_consumed + self.total_cache_read_tokens) * 100)
                if (self.total_tokens_consumed + self.total_cache_read_tokens) > 0 else 0
            )
        }

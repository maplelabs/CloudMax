"""
Cache Metrics Utility

Centralized utilities for extracting and logging LLM prompt caching metrics.
Eliminates duplication between group_triage_service.py and triage_job.py.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def extract_and_log_cache_metrics(
    usage_metadata: Dict[str, Any],
    input_tokens: int,
    context_id: str,
    context_type: str = "triage"
) -> Dict[str, Any]:
    """
    Extract cache metrics from usage metadata and log appropriate messages.

    This function consolidates the cache metrics extraction and logging logic
    that was duplicated across multiple triage service files.

    Args:
        usage_metadata: Dictionary of LLM usage metadata from UsageMetadataCallbackHandler
        input_tokens: Total input tokens used in the operation
        context_id: Identifier for the operation (e.g., "group_id=6" or "triage_id=123 alert_id=456")
        context_type: Type of operation for logging context (default: "triage")

    Returns:
        Dictionary containing extracted cache metrics:
        {
            "total_cache_read": int,
            "total_cache_write": int,
            "cache_hit_rate": float,  # Percentage (0-100)
            "cache_status": str  # One of: "created", "hit", "partial", "none", "edge_case"
        }

    Example:
        >>> usage_metadata = {
        ...     "model_1": {
        ...         "input_token_details": {
        ...             "cache_read": 1000,
        ...             "cache_creation": 0
        ...         }
        ...     }
        ... }
        >>> metrics = extract_and_log_cache_metrics(
        ...     usage_metadata=usage_metadata,
        ...     input_tokens=1500,
        ...     context_id="group_id=6"
        ... )
        >>> print(metrics)
        {'total_cache_read': 1000, 'total_cache_write': 0, 'cache_hit_rate': 66.7, 'cache_status': 'hit'}
    """
    # Extract cache metrics from all models
    total_cache_read = 0
    total_cache_write = 0

    for model_name, llm_usage in usage_metadata.items():
        token_details = llm_usage.get("input_token_details", {})
        cache_read = token_details.get("cache_read", 0)
        cache_creation = token_details.get("cache_creation", 0)

        total_cache_read += cache_read
        total_cache_write += cache_creation

    # Calculate cache hit rate and determine status
    cache_hit_rate = 0.0
    cache_status = "none"

    if input_tokens > 0:
        cache_hit_rate = (total_cache_read / input_tokens) * 100

        # Determine cache status and log appropriately
        if total_cache_write > 0 and total_cache_read == 0:
            # Cache creation - first triage or cache expired
            cache_status = "created"
            logger.info(
                f"{context_id} -> "
                f"CACHE CREATED: {total_cache_write} tokens written to cache (TTL: 1 hour)"
            )
        elif total_cache_read > 0 and total_cache_write == 0:
            # Pure cache hit - optimal scenario
            cache_status = "hit"
            # TODO: Update cost calculation to use actual LLM pricing for caching read and write
            cost_saved = (total_cache_read / 1_000_000) * 0.90
            logger.info(
                f"{context_id} -> "
                f"CACHE HIT: hit_rate={cache_hit_rate:.1f}%, "
                f"cache_read={total_cache_read} tokens (saved ~${cost_saved:.4f})"
            )
        elif total_cache_read > 0 and total_cache_write > 0:
            # Partial cache hit - some agents hit cache, others missed
            cache_status = "partial"
            logger.info(
                f"{context_id} -> "
                f"PARTIAL CACHE: hit_rate={cache_hit_rate:.1f}%, "
                f"cache_read={total_cache_read} tokens, cache_write={total_cache_write} tokens"
            )
        else:
            # No caching activity
            cache_status = "none"
            logger.info(
                f"{context_id} -> "
                f"NO CACHE: cache_read=0 tokens, cache_write=0 tokens"
            )
    elif total_cache_read > 0 or total_cache_write > 0:
        # Edge case: cache activity but no input tokens logged
        cache_status = "edge_case"
        logger.info(
            f"{context_id} -> "
            f"Cache metrics: cache_read={total_cache_read} tokens, "
            f"cache_write={total_cache_write} tokens"
        )

    return {
        "total_cache_read": total_cache_read,
        "total_cache_write": total_cache_write,
        "cache_hit_rate": cache_hit_rate,
        "cache_status": cache_status,
    }


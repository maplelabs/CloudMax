"""
LLM Metrics Tracker - Track LLM call count and latency metrics
Provides observability into LLM performance by tracking call counts and latencies.
"""
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import numpy as np
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class LLMMetricsTracker(BaseCallbackHandler):
    """Track LLM call count and latency metrics."""

    def __init__(self) -> None:
        """Initialize the LLMMetricsTracker."""
        super().__init__()

        # Track start times for each run
        self.run_start_times: Dict[UUID, float] = {}

        # Metrics
        self.api_latencies_sec: List[float] = []
        self.total_llm_calls: int = 0

        logger.info("LLMMetricsTracker: Initialized")
        logger.info("   Tracking: LLM call count and latency (95th percentile)")

    def on_chat_model_start(
            self,
            serialized: Dict[str, Any],
            messages: List[List[BaseMessage]],
            *,
            run_id: UUID,
            parent_run_id: Optional[UUID] = None,
            tags: Optional[List[str]] = None,
            metadata: Optional[Dict[str, Any]] = None,
            **kwargs: Any,
    ) -> Any:
        """Run when a chat model starts running."""
        start_time = time.time()
        self.run_start_times[run_id] = start_time

        logger.debug(f"LLMMetricsTracker: Chat model started (run_id: {run_id})")

    def on_llm_end(
            self,
            response: LLMResult,
            *,
            run_id: UUID,
            parent_run_id: Optional[UUID] = None,
            **kwargs: Any,
    ) -> Any:
        """Run when LLM ends running."""
        end_time = time.time()

        # Check if we have a start time for this run_id
        if run_id not in self.run_start_times:
            logger.warning(
                f"LLMMetricsTracker: on_llm_end called for run_id {run_id} "
                f"without corresponding on_chat_model_start"
            )
            return

        # Calculate latency in seconds
        start_time = self.run_start_times[run_id]
        latency_sec = end_time - start_time

        # Update metrics
        self.api_latencies_sec.append(latency_sec)
        self.total_llm_calls += 1

        # Clean up the run_id from tracking dict
        del self.run_start_times[run_id]

        logger.debug(
            f"LLMMetricsTracker: LLM call completed (run_id: {run_id})"
        )
        logger.debug(f"   Latency: {latency_sec:.3f}s")
        logger.debug(f"   Total calls: {self.total_llm_calls}")

    def get_stats(self) -> Dict[str, Any]:
        """Get LLM metrics statistics."""
        p95_latency_sec = 0.0
        if self.api_latencies_sec:
            p95_latency_sec = float(np.percentile(self.api_latencies_sec, 95))

        return {
            "total_llm_calls": self.total_llm_calls,
            "p95_latency_sec": p95_latency_sec
        }

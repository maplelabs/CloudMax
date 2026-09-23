"""
Group Triage Service

Performs Root Cause Analysis (RCA) on alert groups using LangGraph workflows.
Analyzes all alerts in a group together to identify root cause and cascade timeline.
"""

import json
import logging
import os
import time
from typing import Dict, Any, List, Tuple

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler as LangfuseTracer
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.models.db import AlertDBModel, AlertGroupDBModel
from src.server.utilities.llm_metrics_tracker import LLMMetricsTracker
from src.server.utilities.rate_limiter import TokenRateLimiter
from src.server.utilities.llm_manager import get_primary_llm_price
from src.triage.utilities.cache_metrics import extract_and_log_cache_metrics
from src.triage.workflows.orchestrator import OrchestratorWorkflow

logger = logging.getLogger(__name__)


def capture_ai_analysis(messages, agent_name):
    """Extract the last meaningful AI response from messages."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if (
            isinstance(msg, AIMessage)
            and hasattr(msg, "content")
            and isinstance(msg.content, str)
            and len(msg.content.strip()) > 20
            and not (hasattr(msg, "tool_calls") and msg.tool_calls)
        ):
            logger.info(f"Captured AI analysis from '{agent_name}': {msg.content}")
            return msg.content

    return None


async def triage_alert_group(
    session: AsyncSession | None, group_id: int, thread_id: str
) -> Dict[str, Any]:
    """
    Perform RCA on an alert group using LangGraph workflow.

    Creates a temporary session if needed, fetches group data, then closes the session
    before running the long LangGraph execution to avoid holding database connections.

    Args:
        session: Database session (optional)
        group_id: ID of the alert group to triage
        thread_id: LangGraph thread ID for checkpointing

    Returns:
        Dictionary with RCA results and metrics
    """
    start_time = time.time()
    logger.info(
        f"Starting LangGraph triage for group {group_id} with thread_id={thread_id}"
    )

    should_close_session = session is None
    if should_close_session:
        from src.server.apis_v1.dependencies import async_db_session

        session = async_db_session().__aenter__()
        session = await session

    try:
        # Fetch the group
        stmt = select(AlertGroupDBModel).where(AlertGroupDBModel.id == group_id)
        result = await session.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise ValueError(f"Alert group {group_id} not found")

        # Fetch all alerts in chronological order
        stmt = (
            select(AlertDBModel)
            .where(AlertDBModel.group_id == group_id)
            .order_by(AlertDBModel.created_at.asc())
        )
        result = await session.execute(stmt)
        alerts = result.scalars().all()

        if not alerts:
            raise ValueError(f"No alerts found in group {group_id}")

        logger.info(f"Group {group_id} contains {len(alerts)} alerts")

    finally:
        if should_close_session:
            await session.close()
            logger.info(f"Closed temporary database session for group {group_id}")

    # Build context for LangGraph
    alerts_context = []
    for i, alert in enumerate(alerts, 1):
        payload = alert.payload or {}
        labels = payload.get("labels", {})

        alerts_context.append(
            {
                "sequence": i,
                "alert_id": alert.id,
                "alert_name": alert.alert_name,
                "severity": alert.severity.value if alert.severity else "unknown",
                "timestamp": alert.created_at.isoformat(),
                "source": alert.alert_source,
                "labels": labels,
                "payload": payload,
            }
        )

    group_name = group.group_name
    group_created_at = group.created_at.isoformat()
    group_updated_at = group.updated_at.isoformat()

    group_prompt = f"""
ALERT GROUP TRIAGE REQUEST

Group Name: {group_name}
Total Alerts: {len(alerts)}
Time Range: {group_created_at} to {group_updated_at}

ALERTS IN GROUP (chronological order):
{json.dumps(alerts_context, indent=2, default=str)}

TASK: Perform Root Cause Analysis on this alert group.
Analyze ALL alerts together to identify:
1. The ROOT CAUSE of the incident
2. The TIMELINE of how the incident cascaded
3. The IMPACT on services
4. RECOMMENDED actions to resolve

Focus on identifying the FIRST alert (likely root cause) and understanding how the incident cascaded through the system.
"""

    input_message = HumanMessage(content=group_prompt)

    orchestrator = await OrchestratorWorkflow.build()

    conn_string = os.environ["POSTGRES_CHECKPOINTER_CONN_STRING"]

    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
        await checkpointer.setup()

        compiled_orchestrator = orchestrator.compile(checkpointer=checkpointer)

        usage_callback = UsageMetadataCallbackHandler()
        llm_metrics_tracker = LLMMetricsTracker()

        callbacks: List[BaseCallbackHandler] = [usage_callback, llm_metrics_tracker]

        if os.getenv("ENABLE_TOKEN_RATE_LIMITING", "true").lower() == "true":
            rate_limiter = TokenRateLimiter(usage_callback=usage_callback)
            callbacks.append(rate_limiter)

        if (
            os.environ.get("LANGFUSE_TRACING", "false").lower() == "true"
            and os.environ.get("LANGFUSE_PUBLIC_KEY")
            and os.environ.get("LANGFUSE_SECRET_KEY")
        ):
            try:
                callbacks.append(LangfuseTracer())
                logger.debug(f"group_id={group_id} -> Langfuse tracing enabled")
            except Exception:
                logger.exception(
                    f"group_id={group_id} -> Failed to initialize Langfuse tracing"
                )

        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100,
            "callbacks": callbacks,  # type: ignore
        }

        final_analysis_content = None

        async for chunk in compiled_orchestrator.astream(
            input={"messages": [input_message]},
            stream_mode="updates",
            subgraphs=True,
            config=config,
        ):
            chunk: Tuple

            if len(chunk) >= 2 and len(chunk[0]) > 0:
                for agent_name, value_dict in chunk[1].items():
                    if "messages" in value_dict:
                        messages = value_dict["messages"]
                        final_analysis_content = capture_ai_analysis(
                            messages, agent_name
                        )

        processing_time_sec = int(time.time() - start_time)
        llm_metrics = llm_metrics_tracker.get_stats()

        tokens_used = 0
        price_usd = 0.0

        if usage_callback.usage_metadata is not None:
            total_tokens = sum(
                llm_usage["total_tokens"]
                for llm_usage in usage_callback.usage_metadata.values()
            )

            input_tokens = sum(
                llm_usage.get("input_tokens", 0)
                for llm_usage in usage_callback.usage_metadata.values()
            )

            output_tokens = sum(
                llm_usage.get("output_tokens", 0)
                for llm_usage in usage_callback.usage_metadata.values()
            )

            tokens_used = total_tokens

            llm_price = await get_primary_llm_price()
            price_usd = (input_tokens / 1_000) * llm_price["input"] + (
                output_tokens / 1_000
            ) * llm_price["output"]

            logger.info(
                f"group_id={group_id} -> Tokens: {total_tokens} "
                f"(input: {input_tokens}, output: {output_tokens}), "
                f"Cost: ${price_usd:.4f}"
            )

            # Extract and log cache metrics using centralized utility
            extract_and_log_cache_metrics(
                usage_metadata=usage_callback.usage_metadata,
                input_tokens=input_tokens,
                context_id=f"group_id={group_id}"
            )

        logger.info(
            f"Triage complete for group {group_id}: {final_analysis_content[:100] if final_analysis_content else 'N/A'}"
        )

        return {
            "root_cause_summary": final_analysis_content or "Analysis completed",
            "tokens_used": tokens_used,
            "price_usd": price_usd,
            "processing_time_sec": processing_time_sec,
            "llm_metrics": llm_metrics,
        }

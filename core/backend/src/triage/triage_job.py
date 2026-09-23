"""
Job definitions and enqueue functions for the queue system.
"""
import asyncio
import json
import logging
import os
import re
import time
import traceback
from datetime import datetime
from typing import Any, List, Tuple

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler as LangfuseTracer
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from rq import get_current_job
from sqlalchemy import select

from src.server.apis_v1.dependencies import async_db_session
from src.server.models.api import Status
from src.server.models.db import (
    AlertDBModel,
    EvaluationDBModel,
    RunbookDBModel,
    TriageDBModel,
)
from src.server.utilities import get_queue
from src.server.utilities.config import is_chaos_system_enabled
from src.server.utilities.llm_manager import get_primary_llm_price
from src.server.utilities.llm_metrics_tracker import LLMMetricsTracker
from src.server.utilities.rate_limiter import TokenRateLimiter
from src.triage.utilities.cache_metrics import extract_and_log_cache_metrics
from src.triage.workflows.orchestrator import OrchestratorWorkflow
from src.triage_evaluation import enqueue_evaluation_job

logger = logging.getLogger(__name__)


ERROR_STACKTRACE_MARKERS = [
    "traceback (most recent call last):",
    "exception:",
    "error:",
    "stack trace",
]

# Match common file extensions in stacktraces
FILE_LINE_PATTERN = re.compile(r'File ".*\.(py|js|java|go|cs|rb|php|cpp|c|rs|ts)", line \d+')

# Or even more generic - just look for file paths with line numbers
GENERIC_FILE_LINE_PATTERN = re.compile(r'["\s](/[\w/.-]+\.\w+)["\s:,].*?(\d+)')


def _flatten_payload(obj: Any) -> list[str]:
    """Flatten nested alert payload (dict/list) into a list of strings."""
    texts: list[str] = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            texts.append(str(k))
            texts.extend(_flatten_payload(v))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(_flatten_payload(item))
    elif isinstance(obj, (str, int, float, bool)):
        texts.append(str(obj))

    return texts


def alert_has_error_logs_or_stacktrace(payload: dict) -> bool:
    """Heuristic: does alert payload clearly contain error logs/stack traces?"""
    texts = _flatten_payload(payload)

    for text in texts:
        lower = text.lower()
        if any(marker in lower for marker in ERROR_STACKTRACE_MARKERS):
            return True
        if FILE_LINE_PATTERN.search(text):
            return True
        if GENERIC_FILE_LINE_PATTERN.search(text):
            return True

    return False


def _extract_repository_from_runbook_content(content: str) -> str | None:
    """Extract repository identifier from runbook frontmatter, if present.

    Expected format in the content (YAML frontmatter):

    ---
    repository: owner/repo
    ---
    """
    match = re.search(r"(?m)^repository:\s*([^\s]+)", content)
    if match:
        return match.group(1).strip()
    return None


async def get_repository_from_runbooks(session) -> str | None:
    """Find a repository identifier from stored runbooks, if any.

    This is a best-effort lookup: the first runbook containing a `repository:`
    field in its content is used. This matches the demo setup where runbooks
    include a single repository frontmatter field.
    """
    result = await session.execute(select(RunbookDBModel.content))
    for (content,) in result.all():
        repo = _extract_repository_from_runbook_content(content or "")
        if repo:
            return repo
    return None


def capture_ai_analysis(messages, agent_name):
    """Capture the last meaningful AI analysis from messages."""
    for msg in reversed(messages):
        if (isinstance(msg, AIMessage) and
                hasattr(msg, 'content') and
                isinstance(msg.content, str) and
                len(msg.content.strip()) > 20 and not (hasattr(msg, 'tool_calls') and msg.tool_calls)):
            logger.info(f"Captured AI analysis from '{agent_name}': {msg.content}")
            return msg.content

    return None


async def run_triage_analysis(alert_id: int, triage_id: str):
    """
    Execute the evaluation job asynchronously.

    Args:
        alert_id: Database ID of the alert to evaluate
        triage_id: Thread ID for the triage analysis
    """
    start_time = time.time()

    async with async_db_session() as session:

        alert_data = await session.scalar(select(AlertDBModel).where(AlertDBModel.id == alert_id))
        if not alert_data:
            raise ValueError(f"Alert {alert_id} not found")

        # Find the specific triage record using thread_id (triage_id parameter)
        triage_record = await session.scalar(select(TriageDBModel).where(TriageDBModel.thread_id == triage_id))
        if not triage_record:
            # Fallback to alert_id for backward compatibility, but get the latest one
            triage_record = await session.scalar(
                select(TriageDBModel)
                .where(TriageDBModel.alert_id == alert_id)
                .order_by(TriageDBModel.created_at.desc())
            )
            if not triage_record:
                raise ValueError(f"Triage record not found for alert {alert_id} or thread {triage_id}")

        eval_record = await session.scalar(select(EvaluationDBModel).where(EvaluationDBModel.alert_id == alert_id))
        if not eval_record:
            raise ValueError(f"Evaluation record not found for alert {alert_id}")

        # Cache triage_record.id early to avoid lazy-loading issues after session errors
        triage_record_id = triage_record.id

        try:

            triage_record.status = Status.PROCESSING

            await session.commit()

            logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> Updated status to {Status.PROCESSING}")

            orchestrator = await OrchestratorWorkflow.build()

            # Get repository information from runbooks to enable Code Triage Agent
            repository = await get_repository_from_runbooks(session)

            # Include repository in the alert prompt if available
            alert_prompt = f"Alert:\n{json.dumps(alert_data.payload, indent=2, default=str)}"
            if repository:
                alert_prompt += f"\n\nRepository: {repository}"
                logger.info(f"Added repository '{repository}' to orchestrator input for Code Triage Agent routing")
            else:
                logger.info("No repository found in runbooks; Code Triage Agent may not be used by orchestrator")

            input_message = HumanMessage(content=alert_prompt)

            conn_string = os.environ["POSTGRES_CHECKPOINTER_CONN_STRING"]

            async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:

                await checkpointer.setup()

                compiled_orchestrator = orchestrator.compile(checkpointer=checkpointer)

                usage_callback = UsageMetadataCallbackHandler()
                llm_metrics_tracker = LLMMetricsTracker()

                callbacks: List[BaseCallbackHandler] = [
                    usage_callback,
                    llm_metrics_tracker
                ]

                if os.getenv("ENABLE_TOKEN_RATE_LIMITING", "true").lower() == "true":
                    rate_limiter = TokenRateLimiter(usage_callback=usage_callback)
                    callbacks.append(rate_limiter)

                if (
                        os.environ.get("LANGFUSE_TRACING", "false").lower() == "true" and
                        os.environ.get("LANGFUSE_PUBLIC_KEY") and
                        os.environ.get("LANGFUSE_SECRET_KEY")
                ):

                    try:
                        callbacks.append(LangfuseTracer())
                        logger.debug(f"triage_id={triage_record_id} alert_id={alert_id} -> Langfuse tracing enabled")
                    except Exception:
                        logger.exception(f"triage_id={triage_record_id} alert_id={alert_id} -> "
                                         f"Failed to initialize Langfuse tracing")

                config: RunnableConfig = {
                    "configurable": {"thread_id": triage_id},
                    "recursion_limit": 100,
                    "callbacks": callbacks,  # type: ignore
                }

                final_analysis_content = None
                start_time = time.time()

                # noinspection PyTypeChecker
                async for chunk in compiled_orchestrator.astream(
                        input={
                            "messages": [
                                input_message
                            ]
                        },
                        stream_mode="updates",
                        subgraphs=True,
                        config=config
                ):

                    job = get_current_job()
                    if job:
                        job.meta["status"] = "processing"
                        job.meta["last_update"] = datetime.now().isoformat()
                        job.save_meta()

                    chunk: Tuple

                    if len(chunk) >= 2 and len(chunk[0]) > 0:
                        for agent_name, value_dict in chunk[1].items():
                            if "messages" in value_dict:
                                messages = value_dict["messages"]
                                final_analysis_content = capture_ai_analysis(messages, agent_name)

                # Code Triage Agent is called ONLY by the orchestrator (no forced calls)

                # Update both triage record and alert triage_status
                triage_record.status = Status.SUCCESS
                triage_record.error_message = None
                triage_record.processing_time_sec = int(time.time() - start_time)
                alert_data.triage_status = "success"

                logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> Setting status to SUCCESS")

                triage_record.llm_metrics = llm_metrics_tracker.get_stats()

                logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> "
                            f"LLM metrics: {triage_record.llm_metrics}")

                if usage_callback.usage_metadata is not None:
                    # Calculate total tokens and separate input/output tokens
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

                    triage_record.tokens_used = total_tokens

                    price_config = await get_primary_llm_price()

                    cost_usd = (
                            ((input_tokens / 1000) * price_config["input"]) +
                            ((output_tokens / 1000) * price_config["output"])
                    )

                    triage_record.price_usd = cost_usd

                    logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> "
                                f"Tokens used: {total_tokens} (input: {input_tokens}, output: {output_tokens}), "
                                f"cost: ${cost_usd:.4f}")

                    # Extract and log cache metrics using centralized utility
                    extract_and_log_cache_metrics(
                        usage_metadata=usage_callback.usage_metadata,
                        input_tokens=input_tokens,
                        context_id=f"triage_id={triage_record_id} alert_id={alert_id}"
                    )

                # Final summary
                if final_analysis_content:
                    triage_record.root_cause_summary = final_analysis_content
                    logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> "
                                f"Saved analysis ({len(final_analysis_content)} chars)")
                else:
                    logger.warning(f"triage_id={triage_record_id} alert_id={alert_id} -> No analysis content captured")

                await session.commit()

                logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> Updated status to {Status.SUCCESS}")

            # Check if chaos system is enabled
            chaos_enabled = await is_chaos_system_enabled()

            if not chaos_enabled:
                # Only enqueue evaluation job if chaos system is disabled
                # When chaos is enabled, workflow end will trigger evaluation
                logger.info(f"alert_id={alert_id} -> Chaos system disabled, enqueueing evaluation job")
                eval_job_id = enqueue_evaluation_job(alert_id=alert_id)
                eval_record.job_id = eval_job_id
                eval_record.status = Status.QUEUED
                await session.commit()
            else:
                logger.info(f"alert_id={alert_id} -> Chaos system enabled, will not enqueue evaluation job")
                await session.commit()

        except Exception:

            logger.exception(f"triage_id={triage_record_id} alert_id={alert_id} -> Triage analysis failed")

            try:

                # Update both triage record and alert triage_status
                triage_record.status = Status.ERROR
                triage_record.error_message = traceback.format_exc()
                triage_record.processing_time_sec = int(time.time() - start_time)
                alert_data.triage_status = "failed"
                await session.commit()
                logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> Updated status to {Status.ERROR}")

            except Exception as commit_error:

                logger.exception(f"triage_id={triage_record_id} alert_id={alert_id} -> "
                                 f"Failed to update with error status: {commit_error}")

                try:
                    await session.rollback()
                except Exception:
                    logger.exception(f"triage_id={triage_record_id} alert_id={alert_id} -> Failed to rollback session")

                raise


def execute_triage_analysis_job(alert_id: int, triage_id: str):
    """Execute triage analysis job."""
    job = get_current_job()
    job_id = job.id if job else "unknown"

    logger.info(f"alert_id={alert_id} -> Starting triage job {job_id}")

    try:
        asyncio.run(run_triage_analysis(alert_id, triage_id))
    except Exception:
        logger.exception(f"alert_id={alert_id} -> Failed to execute triage job {job_id}")

        # Update status to ERROR when timeout occurs in sync wrapper
        try:
            asyncio.run(update_triage_status_on_error(alert_id, traceback.format_exc()))
        except Exception as status_error:
            logger.exception(f"alert_id={alert_id} -> Failed to update status after timeout: {status_error}")

    logger.info(f"alert_id={alert_id} -> Completed triage job {job_id}")


async def update_triage_status_on_error(alert_id: int, error_message: str):
    """Update triage status to ERROR when exception occurs in sync wrapper."""
    async with async_db_session() as session:
        # Get the latest triage record for this alert (most recent retry)
        triage_record = await session.scalar(
            select(TriageDBModel)
            .where(TriageDBModel.alert_id == alert_id)
            .order_by(TriageDBModel.created_at.desc())
        )
        if triage_record:
            triage_record_id = triage_record.id  # Cache ID before commit
            triage_record.status = Status.ERROR
            triage_record.error_message = error_message
            await session.commit()
            logger.info(f"triage_id={triage_record_id} alert_id={alert_id} -> Updated status to ERROR after timeout")


def enqueue_triage_job(alert_id: int, triage_id: str, queue_name: str) -> str:
    """
    Enqueue triage job 

    Args:
        alert_id: Database ID of the alert to triage
        triage_id: Thread ID for the triage analysis
        queue_name: Name of the queue to enqueue the job in

    Returns:
        Job ID for tracking
    """
    queue = get_queue(queue_name)

    job = queue.enqueue(
        execute_triage_analysis_job,
        alert_id=alert_id,
        triage_id=triage_id,
        job_timeout="30m"
    )

    logger.info(f"alert_id={alert_id} -> Enqueued triage job {job.id}")

    return job.id
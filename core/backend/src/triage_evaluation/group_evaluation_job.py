"""
Group evaluation job for processing group triage evaluation requests.
Handles the complete evaluation pipeline using DeepEval metrics for alert groups.
"""

import asyncio
import datetime
import logging
import os
import time
from typing import Optional

from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler as LangfuseTracer
from rq import get_current_job
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.server.apis_v1.dependencies import async_db_session
from src.server.apis_v1.helpers import get_formatted_triage_analysis_messages
from src.server.models.api.enums import Status
from src.server.models.db import (
    EvaluationDBModel,
    AlertGroupDBModel,
    FaultLedgerDBModel,
    FaultLedgerToAlertMappingDBModel,
)
from src.server.utilities import get_scheduler, get_queue
from src.server.utilities.config import is_chaos_system_enabled
from .metrics.orchestrator_metrics import OrchestratorMetrics
from .metrics.root_cause_accuracy import RootCauseAccuracyMetric
from .metrics.sub_agent_metrics import SubAgentMetrics
from .utilities import ConversationTurnBuilder, LangGraphLLMWrapper
from .utilities.deepeval_prompt_template import patch_mcp_templates

logger = logging.getLogger(__name__)


async def measure_group_metrics(
    model: LangGraphLLMWrapper,
    group_record: AlertGroupDBModel,
    chaos_system_enabled: bool,
    expected_rca: Optional[str],
):
    """
    Measure all evaluation metrics for a given alert group.

    Args:
        model: LLM wrapper instance
        group_record: Alert group database record
        chaos_system_enabled: Whether to evaluate root cause accuracy
        expected_rca: Expected root cause analysis for comparison

    Returns:
        Dictionary containing all metric scores and reasons
    """
    logger.info(f"Starting metrics evaluation for group_id={group_record.id}")

    # Get formatted messages from group's thread_id
    logger.info(f"Fetching formatted messages for thread_id={group_record.thread_id}")

    messages = await get_formatted_triage_analysis_messages(group_record.thread_id)
    if not messages:
        raise ValueError(f"No messages found for thread_id={group_record.thread_id}")

    logger.info(f"Found {len(messages)} messages for evaluation")

    # Initialize metric classes
    # Use group name and basic info as context
    group_context = {
        "group_name": group_record.group_name,
        "severity": group_record.severity.value if group_record.severity else "Unknown",
    }

    rca_metric = RootCauseAccuracyMetric(model, group_record.group_name, group_context)
    orchestrator_metrics = OrchestratorMetrics(
        model, group_record.group_name, group_context
    )
    sub_agent_metrics = SubAgentMetrics(model, group_record.group_name, group_context)

    await sub_agent_metrics.init_mcp_servers()

    # Evaluate metrics sequentially
    results = dict()

    # 1. Root Cause Accuracy (only if chaos system enabled and expected RCA provided)
    if chaos_system_enabled and expected_rca:
        logger.info("Evaluating root cause accuracy")
        results["root_cause_accuracy"] = await rca_metric.evaluate(
            messages=messages, expected_rca=expected_rca
        )

    # Build conversations once via ConversationTurnBuilder
    builder = ConversationTurnBuilder(messages)

    orch_turns = builder.get_orchestrator_conversation()

    # 2. Orchestrator Coordination
    logger.info("Evaluating orchestrator coordination")
    results["orchestrator_coordination"] = (
        await orchestrator_metrics.evaluate_agent_utilization(turns=orch_turns)
    )

    # 3. Orchestrator Task Completion
    logger.info("Evaluating orchestrator task completion")
    results["orchestrator_task_completion"] = (
        await orchestrator_metrics.evaluate_task_completion(turns=orch_turns)
    )

    # Sub-agent conversations
    sub_agent_conversations = builder.get_sub_agents_conversations()

    # 4. Sub-Agent Tool Utilization
    logger.info("Evaluating sub-agent tool utilization")
    results["sub_agent_tool_utilization"] = (
        await sub_agent_metrics.evaluate_tool_utilization(
            sub_agent_conversations=sub_agent_conversations
        )
    )

    # 5. Sub-Agent Task Completion
    logger.info("Evaluating sub-agent task completion")
    results["sub_agent_task_completion"] = (
        await sub_agent_metrics.evaluate_task_completion(
            sub_agent_conversations=sub_agent_conversations
        )
    )

    logger.info(f"All metrics evaluated for group_id={group_record.id}")

    return results


async def _execute_group_evaluation_job_async(group_id: int):
    """
    Async implementation of group evaluation job.

    Args:
        group_id: Alert group ID to evaluate
    """
    start_time = time.time()

    # Patch DeepEval templates
    patch_mcp_templates()

    async with async_db_session() as session:
        # Fetch group record with alerts eagerly loaded
        group_record = await session.scalar(
            select(AlertGroupDBModel)
            .options(selectinload(AlertGroupDBModel.alerts))
            .where(AlertGroupDBModel.id == group_id)
        )

        if not group_record:
            raise ValueError(f"Alert group {group_id} not found")

        # Get evaluation record
        eval_record = await session.scalar(
            select(EvaluationDBModel).where(EvaluationDBModel.group_id == group_id)
        )

        if not eval_record:
            raise ValueError(f"Evaluation record for group {group_id} not found")

        # Check triage status - requeue if not complete
        if group_record.triage_status in ["pending", "in_progress"]:
            logger.info(
                f"group_id={group_id} -> Triage still in progress (status={group_record.triage_status}), retry later"
            )

            scheduler = get_scheduler("group_evaluations")

            # Schedule the job to run after 1 minute
            job = scheduler.enqueue_in(
                datetime.timedelta(minutes=1),
                execute_group_evaluation_job,
                group_id=group_id,
                job_timeout="30m",
            )

            eval_record.job_id = job.id
            await session.commit()

            logger.info(
                f"group_id={group_id} -> Requeued evaluation job with job_id={job.id} to run in 1 minute"
            )
            return

        if group_record.triage_status == "failed":
            logger.error(
                f"group_id={group_id} -> Triage failed, not running evaluation"
            )
            eval_record.status = Status.ERROR
            eval_record.error_message = "Triage failed, evaluation skipped"
            await session.commit()
            return

        # Fetch chaos system configuration
        chaos_system_enabled = await is_chaos_system_enabled()

        # FIXED: Fetch expected RCA from fault ledger if chaos enabled
        expected_rca = None

        if chaos_system_enabled:
            # Find fault ledger through any alert in the group
            # All alerts in a group should map to the same fault ledger
            if group_record.alerts and len(group_record.alerts) > 0:
                alert_in_group = group_record.alerts[0]
                logger.info(
                    f"group_id={group_id} -> Checking fault ledger mapping for alert_id={alert_in_group.id}"
                )

                fault_mapping = await session.scalar(
                    select(FaultLedgerToAlertMappingDBModel).where(
                        FaultLedgerToAlertMappingDBModel.alert_id == alert_in_group.id
                    )
                )

                if fault_mapping:
                    fault_ledger = await session.scalar(
                        select(FaultLedgerDBModel).where(
                            FaultLedgerDBModel.id == fault_mapping.fault_ledger_id
                        )
                    )

                    if fault_ledger:
                        expected_rca = fault_ledger.fault_description
                        logger.info(
                            f"group_id={group_id} -> Found fault ledger {fault_ledger.id}, expected_rca: {expected_rca[:100]}..."
                        )
                    else:
                        logger.warning(
                            f"group_id={group_id} -> Fault mapping exists but fault ledger not found"
                        )
                else:
                    logger.info(
                        f"group_id={group_id} -> No fault ledger mapping found for this group"
                    )
            else:
                logger.warning(
                    f"group_id={group_id} -> Group has no alerts, cannot fetch fault ledger"
                )

        try:
            eval_record.status = Status.PROCESSING
            await session.commit()

            logger.info(
                f"eval_id={eval_record.id} group_id={group_id} -> Updated status to {Status.PROCESSING}"
            )

            # Initialize LLM wrapper
            model = LangGraphLLMWrapper()
            await model._initialize_model()

            # Measure all metrics with optional Langfuse tracing
            metrics = None
            if (
                os.environ.get("LANGFUSE_TRACING", "false").lower() == "true"
                and os.environ.get("LANGFUSE_PUBLIC_KEY")
                and os.environ.get("LANGFUSE_SECRET_KEY")
            ):
                try:
                    langfuse_client = get_client()
                    langfuse_tracer = LangfuseTracer()

                    session_id = f"evaluation-group-{group_id}-{eval_record.id}"

                    with langfuse_client.start_as_current_observation(
                        as_type="span",
                        name=f"evaluation-group-{group_id}",
                    ):
                        with propagate_attributes(session_id=session_id):
                            model.callbacks.append(langfuse_tracer)

                            metrics = await measure_group_metrics(
                                model=model,
                                group_record=group_record,
                                chaos_system_enabled=chaos_system_enabled,
                                expected_rca=expected_rca,
                            )

                    logger.debug(
                        f"eval_id={eval_record.id} group_id={group_id} -> Langfuse tracing enabled with session: {session_id}"
                    )

                except Exception:
                    logger.exception(
                        f"eval_id={eval_record.id} group_id={group_id} -> Failed to initialize Langfuse tracing"
                    )
                    # Fall back to running without tracing
                    metrics = await measure_group_metrics(
                        model=model,
                        group_record=group_record,
                        chaos_system_enabled=chaos_system_enabled,
                        expected_rca=expected_rca,
                    )

            else:
                # Run without tracing
                metrics = await measure_group_metrics(
                    model=model,
                    group_record=group_record,
                    chaos_system_enabled=chaos_system_enabled,
                    expected_rca=expected_rca,
                )

            # Log the metrics to debug
            logger.info(f"group_id={group_id} -> Evaluation metrics keys: {list(metrics.keys())}")
            for metric_name, metric_data in metrics.items():
                if metric_data:
                    score = metric_data.get('score')
                    reason_preview = metric_data.get('reason', '')[:100] if metric_data.get('reason') else 'N/A'
                    logger.info(f"group_id={group_id} -> {metric_name}: score={score}, reason_preview={reason_preview}...")

            # Collect LLM metrics
            llm_metrics = model.llm_metrics_tracker.get_stats()

            # Set final status and save results
            eval_record.status = Status.SUCCESS
            eval_record.error_message = None
            eval_record.processing_time_sec = int(time.time() - start_time)

            logger.info(
                f"eval_id={eval_record.id} group_id={group_id} -> Setting status to SUCCESS"
            )

            # Save evaluation scores
            if metrics.get("root_cause_accuracy") is not None:
                rca_score = metrics["root_cause_accuracy"].get("score")
                if rca_score is not None:
                    # Ensure score is an integer (database column is Integer type)
                    eval_record.root_cause_similarity_percent = int(rca_score)
                    logger.info(f"group_id={group_id} -> Saved RCA score: {int(rca_score)}")
                else:
                    logger.warning(f"group_id={group_id} -> RCA metric exists but score is None")

            if metrics.get("orchestrator_coordination") is not None:
                orch_coord_score = metrics["orchestrator_coordination"].get("score")
                if orch_coord_score is not None:
                    eval_record.orch_agent_util_score_percent = int(orch_coord_score)
                else:
                    logger.warning(f"group_id={group_id} -> Orchestrator coordination metric exists but score is None")

            if metrics.get("orchestrator_task_completion") is not None:
                orch_task_score = metrics["orchestrator_task_completion"].get("score")
                if orch_task_score is not None:
                    eval_record.orch_task_completion_score_percent = int(orch_task_score)
                else:
                    logger.warning(f"group_id={group_id} -> Orchestrator task completion metric exists but score is None")

            if metrics.get("sub_agent_tool_utilization") is not None:
                sub_tool_score = metrics["sub_agent_tool_utilization"].get("score")
                if sub_tool_score is not None:
                    eval_record.sub_agent_tool_util_score_percent = int(sub_tool_score)
                else:
                    logger.warning(f"group_id={group_id} -> Sub-agent tool utilization metric exists but score is None")

            if metrics.get("sub_agent_task_completion") is not None:
                sub_task_score = metrics["sub_agent_task_completion"].get("score")
                if sub_task_score is not None:
                    eval_record.sub_agent_task_completion_score = int(sub_task_score)
                else:
                    logger.warning(f"group_id={group_id} -> Sub-agent task completion metric exists but score is None")

            # Generate formatted summary using LLM (same as individual alerts)
            from src.triage_evaluation.evaluation_job import generate_evaluation_summary

            reason_for_summary = ""
            if metrics is None:
                eval_record.reason = "No evaluation metrics available for summary."
            else:
                # Only include metrics that have valid scores (not None/null)
                # This filters out RCA if it wasn't calculated due to missing expected RCA
                reason_for_summary = "\n".join(
                    f"{metric_name}: {result['reason']}"
                    for metric_name, result in metrics.items()
                    if result is not None and result.get('score') is not None
                )

            # Generate markdown-formatted summary with proper headings
            summary = await generate_evaluation_summary(reason_for_summary, model)
            eval_record.reason = summary

            # Save LLM metrics
            eval_record.tokens_used = llm_metrics.get("total_tokens", 0)
            eval_record.price_usd = llm_metrics.get("total_cost", 0.0)
            eval_record.llm_metrics = llm_metrics

            await session.commit()

            logger.info(
                f"eval_id={eval_record.id} group_id={group_id} -> Evaluation completed successfully"
            )

        except Exception as e:
            logger.exception(
                f"eval_id={eval_record.id} group_id={group_id} -> Evaluation failed"
            )
            eval_record.status = Status.ERROR
            eval_record.error_message = str(e)
            eval_record.processing_time_sec = int(time.time() - start_time)
            await session.commit()
            raise


def execute_group_evaluation_job(group_id: int):
    """
    RQ job entry point for group evaluation.

    Args:
        group_id: Alert group ID to evaluate
    """
    job = get_current_job()
    logger.info(f"Starting group evaluation job: job_id={job.id}, group_id={group_id}")

    try:
        asyncio.run(_execute_group_evaluation_job_async(group_id))
        logger.info(
            f"Group evaluation job completed: job_id={job.id}, group_id={group_id}"
        )

    except Exception:
        logger.exception(
            f"Group evaluation job failed: job_id={job.id}, group_id={group_id}"
        )
        raise


def enqueue_group_evaluation_job(group_id: int) -> str:
    """
    Enqueue a group evaluation job for processing.

    Args:
        group_id: Database ID of the alert group to evaluate

    Returns:
        Job ID for tracking
    """
    try:
        queue = get_queue("group_evaluations")

        job = queue.enqueue(
            execute_group_evaluation_job, group_id=group_id, job_timeout="30m"
        )

        logger.info(f"group_id={group_id} -> Enqueued group evaluation job {job.id}")

        return job.id

    except Exception:
        logger.exception(
            f"group_id={group_id} -> Failed to enqueue group evaluation job"
        )
        raise

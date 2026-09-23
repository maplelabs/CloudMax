"""
Evaluation job for processing RCA evaluation requests.
Handles the complete evaluation pipeline using DeepEval metrics.
"""
import asyncio
import datetime
import logging
import os
import time
import traceback
from typing import Dict, Any, Optional

from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler as LangfuseTracer
from rq import get_current_job
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.server.apis_v1.dependencies import async_db_session
from src.server.apis_v1.helpers import get_formatted_triage_analysis_messages
from src.server.models.api.enums import Status
from src.server.models.db import EvaluationDBModel, AlertDBModel, TriageDBModel
from src.server.utilities import get_queue, get_scheduler
from src.server.utilities.config import is_chaos_system_enabled
from src.server.utilities.llm_manager import get_secondary_llm_price
from .metrics.orchestrator_metrics import OrchestratorMetrics
from .metrics.root_cause_accuracy import RootCauseAccuracyMetric
from .metrics.sub_agent_metrics import SubAgentMetrics
from .utilities import ConversationTurnBuilder, LangGraphLLMWrapper
from .utilities.deepeval_prompt_template import patch_mcp_templates

logger = logging.getLogger(__name__)


async def measure_all_metrics(
        model: LangGraphLLMWrapper,
        alert_record: AlertDBModel,
        triage_record: TriageDBModel,
        chaos_system_enabled: bool,
        expected_rca: Optional[str]
) -> Dict[str, Any]:
    """
    Measure all evaluation metrics for a given alert.

    Args:
        model: LLM wrapper instance
        alert_record: Alert database record
        triage_record: Triage database record
        chaos_system_enabled: Whether to evaluate root cause accuracy
        expected_rca: Expected root cause analysis for comparison

    Returns:
        Dictionary containing all metric scores and reasons
    """
    logger.info(f"Starting metrics evaluation for alert_id={alert_record.id}")

    # Get formatted messages
    logger.info(f"Fetching formatted messages for thread_id={triage_record.thread_id}")

    messages = await get_formatted_triage_analysis_messages(triage_record.thread_id)
    if not messages:
        raise ValueError(f"No messages found for thread_id={triage_record.thread_id}")

    logger.info(f"Found {len(messages)} messages for evaluation")

    # Initialize metric classes
    rca_metric = RootCauseAccuracyMetric(model, alert_record.alert_name, alert_record.payload)
    orchestrator_metrics = OrchestratorMetrics(model, alert_record.alert_name, alert_record.payload)
    sub_agent_metrics = SubAgentMetrics(model, alert_record.alert_name, alert_record.payload)

    await sub_agent_metrics.init_mcp_servers()

    # Evaluate metrics sequentially. We can do it async for faster evaluation but will need to handle throttle better
    results = dict()

    # 1. Root Cause Accuracy (only if chaos system enabled)
    if chaos_system_enabled:
        logger.info("Evaluating root cause accuracy")
        results["root_cause_accuracy"] = await rca_metric.evaluate(
            messages=messages,
            expected_rca=expected_rca
        )

    # Build conversations once via ConversationTurnBuilder
    builder = ConversationTurnBuilder(messages)

    orch_turns = builder.get_orchestrator_conversation()

    # 2. Orchestrator Coordination (with pre-built turns)
    logger.info("Evaluating orchestrator coordination")
    results["orchestrator_coordination"] = await orchestrator_metrics.evaluate_agent_utilization(
        turns=orch_turns
    )

    # 3. Orchestrator Task Completion (with pre-built turns)
    logger.info("Evaluating orchestrator task completion")
    results["orchestrator_task_completion"] = await orchestrator_metrics.evaluate_task_completion(
        turns=orch_turns
    )

    # Sub-agent conversations: List[(agent_name, turns)]
    sub_agent_conversations = builder.get_sub_agents_conversations()

    # 4. Sub-Agent Tool Utilization (with pre-built turn sets)
    logger.info("Evaluating sub-agent tool utilization")
    results["sub_agent_tool_utilization"] = await sub_agent_metrics.evaluate_tool_utilization(
        sub_agent_conversations=sub_agent_conversations
    )

    # 5. Sub-Agent Task Completion (with pre-built turn sets)
    logger.info("Evaluating sub-agent task completion")
    results["sub_agent_task_completion"] = await sub_agent_metrics.evaluate_task_completion(
        sub_agent_conversations=sub_agent_conversations
    )

    logger.info(f"Completed metrics evaluation for alert_id={alert_record.id}")

    return results


async def generate_evaluation_summary(reasons: str, model: LangGraphLLMWrapper) -> str:
    """
    Generate a concise 2-3 line summary of all evaluation metrics using LLM.
    
    Args:
        reasons: Concatenated reasons from all metrics
        model: LLM wrapper instance
        
    Returns:
        Concise summary string
    """
    chaos_system_enabled = await is_chaos_system_enabled()

    # Use exact same names as score card titles in the UI
    metrics_list = ["- Orchestrator Agent Utilization",
                    "- Orchestrator Task Completion",
                    "- Sub-Agent Tool Utilization",
                    "- Sub-Agent Task Completion"]

    if chaos_system_enabled:
        metrics_list.insert(0, "- Root Cause Similarity")

    try:
        if reasons == "No evaluation metrics available for summary.":
            return "No evaluation metrics available for summary."

        prompt = f"""
You are an AI evaluation analyst generating a well-structured markdown summary of evaluation results.

CRITICAL FORMATTING RULES:
1. Use markdown heading ## for each metric section
2. Each metric MUST start with: ## [Metric Name]
3. Follow each heading with 2-3 paragraphs
4. Use proper heading format with spaces (NOT underscores)

STRUCTURE:
```
## Root Cause Similarity

[2-3 sentences of analysis from evaluation results]

[Overall outcome statement]

## Orchestrator Agent Utilization

[2-3 sentences of analysis from evaluation results]

[Overall outcome statement]
```

GUIDELINES:
- Describe observable behavior factually
- Highlight effectiveness and completion success
- End each section with: "The outcome was good" or "The outcome was satisfactory"
- Keep each section concise (2-3 sentences)

EVALUATION RESULTS:
{reasons}

Use ONLY these metric names as ## headings:
"""
        prompt += "\n".join([name.replace("- ", "") for name in metrics_list])
        prompt += "\n\nGenerate markdown summary with ## headings for each metric."

        response = await model.a_generate(prompt)
        summary = response.strip()
        return summary.strip()

    except Exception as e:
        logger.warning(f"Failed to generate LLM summary: {e}")
        # Fallback to simple summary
        return "Evaluation completed. Check individual scores for detailed performance analysis."


async def run_evaluation_analysis(alert_id: int):
    """
    Execute the evaluation job asynchronously.

    Args:
        alert_id: Database ID of the alert to evaluate
    """
    start_time = time.time()
    patch_mcp_templates()
    async with async_db_session() as session:

        # Get alert with eager loading of chaos workflow relationship
        alert_record = await session.scalar(
            select(
                AlertDBModel
            )
            .where(
                AlertDBModel.id == alert_id
            )
            .options(
                selectinload(
                    AlertDBModel.fault_ledger
                )
            )
        )

        if not alert_record:
            raise ValueError(f"Alert {alert_id} not found")

        triage_record = await session.scalar(
            select(
                TriageDBModel
            ).
            where(
                TriageDBModel.alert_id == alert_id
            ).
            order_by(TriageDBModel.created_at.desc())
        )

        if not triage_record:
            raise ValueError(f"Triage record for alert {alert_id} not found")

        # Get the LATEST evaluation record (by created_at) to handle cases where multiple evaluations exist
        eval_record = await session.scalar(
            select(
                EvaluationDBModel
            ).
            where(
                EvaluationDBModel.alert_id == alert_id
            ).
            order_by(EvaluationDBModel.created_at.desc())
        )

        if not eval_record:
            raise ValueError(f"Evaluation record for alert {alert_id} not found")

        # Check triage status - requeue if not complete
        if triage_record.status in [Status.QUEUED, Status.PROCESSING]:
            logger.info(f"alert_id={alert_id} -> Triage still in progress (status={triage_record.status}), retry later")

            scheduler = get_scheduler("triages_to_evaluate")

            # Schedule the job to run after 1 minute
            job = scheduler.enqueue_in(
                datetime.timedelta(minutes=1),
                execute_evaluation_job,
                alert_id=alert_id,
                timeout='30m'
            )

            eval_record.job_id = job.id
            await session.commit()

            logger.info(f"alert_id={alert_id} -> Requeued evaluation job with job_id={job.id} to run in 1 minute")

            return

        if triage_record.status == Status.ERROR:
            logger.error(f"alert_id={alert_id} -> Triage failed, not running evaluation")
            eval_record.status = Status.ERROR
            eval_record.error_message = "Triage failed, evaluation skipped"
            await session.commit()
            return

        # Fetch chaos system configuration
        chaos_system_enabled = await is_chaos_system_enabled()

        # Get expected RCA from fault ledger if chaos is enabled
        expected_rca = None
        if chaos_system_enabled and alert_record.fault_ledger:
            expected_rca = alert_record.fault_ledger.fault_description

        try:
            eval_record.status = Status.PROCESSING

            await session.commit()

            logger.info(f"eval_id={eval_record.id} alert_id={alert_id} -> Updated status to {Status.PROCESSING}")

            # Update job metadata during processing (following triage job pattern)
            job = get_current_job()
            if job:
                job.meta['status'] = 'processing'
                job.meta['last_update'] = datetime.datetime.now().isoformat()
                job.save_meta()

            # Run all metrics evaluation using measure_all_metrics function
            logger.info(f"eval_id={eval_record.id} alert_id={alert_id} -> Running all metrics evaluation")

            model = LangGraphLLMWrapper()
            await model._initialize_model()
            metrics = None
            if (
                    os.environ.get("LANGFUSE_TRACING", "false").lower() == "true" and
                    os.environ.get("LANGFUSE_PUBLIC_KEY") and
                    os.environ.get("LANGFUSE_SECRET_KEY")
            ):
                try:
                    langfuse_client = get_client()
                    langfuse_tracer = LangfuseTracer()

                    session_id = f"evaluation-alert-{alert_id}-{eval_record.id}"

                    with langfuse_client.start_as_current_observation(
                            as_type="span",
                            name=f"evaluation-alert-{alert_id}",
                    ):
                        with propagate_attributes(session_id=session_id):
                            model.callbacks.append(langfuse_tracer)

                            metrics = await measure_all_metrics(
                                model=model,
                                alert_record=alert_record,
                                triage_record=triage_record,
                                chaos_system_enabled=chaos_system_enabled,
                                expected_rca=expected_rca
                            )

                    logger.debug(
                        f"eval_id={eval_record.id} alert_id={alert_id} -> Langfuse tracing enabled with session: {session_id}")

                except Exception:
                    logger.exception(
                        f"eval_id={eval_record.id} alert_id={alert_id} -> Failed to initialize Langfuse tracing")
                    metrics = await measure_all_metrics(
                        model=model,
                        alert_record=alert_record,
                        triage_record=triage_record,
                        chaos_system_enabled=chaos_system_enabled,
                        expected_rca=expected_rca
                    )

            else:
                metrics = await measure_all_metrics(
                    model=model,
                    alert_record=alert_record,
                    triage_record=triage_record,
                    chaos_system_enabled=chaos_system_enabled,
                    expected_rca=expected_rca
                )

            # Set final status and save results (following triage job pattern)
            eval_record.status = Status.SUCCESS
            eval_record.error_message = None
            eval_record.processing_time_sec = int(time.time() - start_time)

            logger.info(f"eval_id={eval_record.id} alert_id={alert_id} -> Setting status to SUCCESS")

            # Save evaluation scores using new format
            if metrics.get('root_cause_accuracy') is not None:
                eval_record.root_cause_similarity_percent = metrics['root_cause_accuracy']['score']

            if metrics.get('orchestrator_coordination') is not None:
                eval_record.orch_agent_util_score_percent = metrics['orchestrator_coordination']['score']

            if metrics.get('orchestrator_task_completion') is not None:
                eval_record.orch_task_completion_score_percent = metrics['orchestrator_task_completion']['score']

            if metrics.get('sub_agent_tool_utilization') is not None:
                eval_record.sub_agent_tool_util_score_percent = metrics['sub_agent_tool_utilization']['score']

            if metrics.get('sub_agent_task_completion') is not None:
                eval_record.sub_agent_task_completion_score = metrics['sub_agent_task_completion']['score']

            eval_record.llm_metrics = model.llm_metrics_tracker.get_stats()

            # Calculate tokens and cost
            if model.usage_callback.usage_metadata is not None:
                total_tokens = sum(
                    llm_usage["total_tokens"]
                    for llm_usage in model.usage_callback.usage_metadata.values()
                )

                input_tokens = sum(
                    llm_usage.get("input_tokens", 0)
                    for llm_usage in model.usage_callback.usage_metadata.values()
                )

                output_tokens = sum(
                    llm_usage.get("output_tokens", 0)
                    for llm_usage in model.usage_callback.usage_metadata.values()
                )

                eval_record.tokens_used = total_tokens

                price_config = await get_secondary_llm_price()

                # Calculate cost: (input_tokens / 1000 * price_per_1k_ip) + (output_tokens / 1000 * price_per_1k_op)
                cost_usd = (
                        ((input_tokens / 1000) * price_config["input"]) +
                        ((output_tokens / 1000) * price_config["output"])
                )

                eval_record.price_usd = cost_usd

                logger.info(f"eval_id={eval_record.id} alert_id={alert_id} -> "
                            f"Tokens used: {total_tokens} (input: {input_tokens}, output: {output_tokens}), "
                            f"cost: ${cost_usd:.4f}")

            reason_for_summary = ""

            if metrics is None:
                eval_record.reason = "No evaluation metrics available for summary."
            else:
                # Only include metrics that have valid scores (not None/null)
                # This filters out RCA if it wasn't calculated due to missing expected RCA
                reason_for_summary = "\n".join(f"{metric_name}: {result['reason']}"
                                               for metric_name, result in metrics.items()
                                               if result is not None and result.get('score') is not None)

            summary = await generate_evaluation_summary(reason_for_summary, model)

            eval_record.reason = summary

            await session.commit()

            logger.info(f"eval_id={eval_record.id} alert_id={alert_id} -> Updated status to {Status.SUCCESS}")

        except Exception:

            logger.exception(f"eval_id={eval_record.id} alert_id={alert_id} -> Evaluation analysis failed")

            try:
                eval_record.status = Status.ERROR
                eval_record.error_message = traceback.format_exc()
                eval_record.processing_time_sec = int(time.time() - start_time)
                await session.commit()
                logger.info(f"eval_id={eval_record.id} alert_id={alert_id} -> Updated status to {Status.ERROR}")

            except Exception:

                logger.exception(f"eval_id={eval_record.id} alert_id={alert_id} -> Failed to update evaluation")

                try:
                    await session.rollback()
                except Exception:
                    logger.exception(f"eval_id={eval_record.id} alert_id={alert_id} -> Failed to rollback session")

                raise


def execute_evaluation_job(alert_id: int):
    """
    Execute the evaluation job synchronously.

    Args:
        alert_id: Database ID of the alert to evaluate

    Returns:
        Dictionary containing evaluation results
    """
    job = get_current_job()
    job_id = job.id if job else "unknown"

    logger.info(f"alert_id={alert_id} -> Starting evaluation job {job_id}")
    start_time = time.time()

    try:
        asyncio.run(run_evaluation_analysis(alert_id))
    except Exception:
        logger.exception(f"alert_id={alert_id} -> Failed to execute evaluation job {job_id}")

    processing_time = time.time() - start_time

    logger.info(f"alert_id={alert_id} -> Completed evaluation job {job_id} in {processing_time:.2f}s")


def enqueue_evaluation_job(alert_id: int) -> str:
    """
    Enqueue an evaluation job for processing.

    Args:
        alert_id: Database ID of the alert to evaluate

    Returns:
        Job ID for tracking
    """
    try:
        queue = get_queue("triages_to_evaluate")

        job = queue.enqueue(
            execute_evaluation_job,
            alert_id=alert_id,
            job_timeout='30m'
        )

        logger.info(f"alert_id={alert_id} -> Enqueued evaluation job {job.id}")

        return job.id

    except Exception:

        logger.exception(f"alert_id={alert_id} -> Failed to enqueue evaluation job")
        raise

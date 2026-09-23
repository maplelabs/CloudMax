"""
Helper functions for alert database operations.

This module contains centralized helper functions for fetching alert details
from the database, used by the alerts API endpoints.
"""
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Union, Dict

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.models.api.alert_traige import TriageAIMessage, TriageToolMessage
from src.server.models.api.enums import Status, ToolResponseType
from src.server.models.db import AlertDBModel, TriageDBModel, EvaluationDBModel
from src.server.utilities import get_triage_analysis_data

logger = logging.getLogger(__name__)


def generate_triage_thread_id(alert_id: int) -> str:
    """
    Generate a unique thread ID for triage analysis.

    Args:
        alert_id: Database ID of the alert

    Returns:
        Unique thread ID in format: triage_{alert_id}_{random_hex}
    """
    return f"triage_{alert_id}_{uuid.uuid4().hex[:8]}"


async def get_alert_by_id(alert_id: str, session: AsyncSession) -> AlertDBModel:
    """
    Retrieve alert by ID from database.

    Args:
        alert_id: Alert identifier (can be database ID or external_id)
        session: Database session

    Returns:
        Alert object

    Raises:
        HTTPException: If alert not found
    """
    try:
        # Try to parse as integer ID first, otherwise use as external_id
        try:
            numeric_id = int(alert_id)
            stmt = select(AlertDBModel).where(AlertDBModel.id == numeric_id)
        except ValueError:
            # Not a number, treat as external_id
            stmt = select(AlertDBModel).where(AlertDBModel.external_id == alert_id)

        result = await session.execute(stmt)
        alert = result.scalar_one_or_none()

        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert with ID '{alert_id}' not found"
            )

        return alert

    except HTTPException:
        raise

    except SQLAlchemyError:

        logger.exception(f"Database error retrieving alert {alert_id}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving alert"
        )


async def get_latest_triage_record(alert_id: int, session: AsyncSession) -> Optional[TriageDBModel]:
    """
    Get the latest (most recent) triage record for a given alert ID.

    Args:
        alert_id: Alert database ID
        session: Database session

    Returns:
        Latest Triage record or None if no triage records exist
    """
    try:
        stmt = (
            select(TriageDBModel).
            where(TriageDBModel.alert_id == alert_id).
            order_by(TriageDBModel.created_at.desc()).limit(1)
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    except SQLAlchemyError:

        logger.exception(f"Database error retrieving latest triage record for alert {alert_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving latest triage record"
        )


async def get_triage_records_for_alert(alert_id: int, session: AsyncSession) -> List[TriageDBModel]:
    """
    Retrieve all triage records for a given alert ID.

    Args:
        alert_id: Alert database ID
        session: Database session

    Returns:
        List of Triage objects ordered by created_at desc
    """
    try:
        stmt = select(TriageDBModel).where(TriageDBModel.alert_id == alert_id).order_by(TriageDBModel.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())
    except SQLAlchemyError:
        logger.exception(f"Database error retrieving triage records for alert {alert_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving triage records"
        )


async def get_eval_records_for_alert(alert_id: int, session: AsyncSession) -> List[EvaluationDBModel]:
    """
    Retrieve all evaluation records for a given alert ID.

    Args:
        alert_id: Alert database ID
        session: Database session

    Returns:
        List of Triage objects ordered by created_at desc
    """
    try:

        stmt = (
            select(EvaluationDBModel).
            where(EvaluationDBModel.alert_id == alert_id).
            order_by(EvaluationDBModel.created_at.desc())
        )

        result = await session.execute(stmt)

        return list(result.scalars().all())

    except SQLAlchemyError:

        logger.exception(f"Database error retrieving evaluation records for alert {alert_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving evaluation records"
        )


async def get_latest_evaluation_record(alert_id: int, session: AsyncSession) -> Optional[EvaluationDBModel]:
    """
    Get the latest (most recent) evaluation record for a given alert ID.

    Args:
        alert_id: Alert database ID
        session: Database session

    Returns:
        Latest Evaluation record or None if no evaluation records exist
    """
    try:
        stmt = (
            select(EvaluationDBModel).
            where(EvaluationDBModel.alert_id == alert_id).
            order_by(EvaluationDBModel.created_at.desc()).limit(1)
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    except SQLAlchemyError:
        logger.exception(f"Database error retrieving latest evaluation record for alert {alert_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving latest evaluation record"
        )


async def get_latest_group_evaluation_record(group_id: int, session: AsyncSession) -> Optional[EvaluationDBModel]:
    """
    Get the latest (most recent) evaluation record for a given alert group ID.

    Args:
        group_id: Alert group database ID
        session: Database session

    Returns:
        Latest Evaluation record or None if no evaluation records exist
    """
    try:
        stmt = (
            select(EvaluationDBModel).
            where(EvaluationDBModel.group_id == group_id).
            order_by(EvaluationDBModel.created_at.desc()).limit(1)
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    except SQLAlchemyError:
        logger.exception(f"Database error retrieving latest evaluation record for group {group_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving latest group evaluation record"
        )


def _extract_content(content):
    """Extract string content from various content formats."""
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        # ChatBedrockConverse returns list of content blocks
        text_parts = []
        for block in content:
            if isinstance(block, dict) and 'text' in block:
                text_parts.append(block['text'])
        return ' '.join(text_parts).strip()
    else:
        return str(content).strip()


async def get_formatted_triage_analysis_messages(thread_id: str) -> List[Union[TriageAIMessage, TriageToolMessage]]:
    """
    Format triage analysis data into TriageAIMessage and TriageToolMessage objects.

    Args:
        thread_id: Thread ID for the triage analysis

    Returns:
        List of formatted triage messages

    Raises:
        Does not raise exceptions - logs warnings and returns empty list on errors
    """
    messages = []

    try:

        logger.info(f"Fetching triage analysis data for thread_id: {thread_id}")

        analysis_data = await get_triage_analysis_data(thread_id)

        tool_usage: Dict[str, Dict[str, str]] = dict()
        current_active_agent = "Alert_Triage_Orchestrator"  # Track the currently active agent

        if analysis_data and analysis_data.get("all_messages"):

            # Convert analysis messages to the expected format
            for msg_data in analysis_data["all_messages"]:

                msg_type = msg_data.get("type", "").strip()
                content = _extract_content(msg_data.get("content", ""))
                timestamp = msg_data.get("timestamp")
                tool_calls = msg_data.get("tool_calls", list())

                # Convert to datetime if timestamp is a string
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        # If datetime parsing fails, use current time
                        timestamp = datetime.now()

                elif timestamp is None:
                    timestamp = datetime.now()

                # Only process Tool and AI messages
                if msg_type == "AIMessage":

                    # Agent name mapping: lowercase (from langgraph_supervisor) -> Display name
                    # langgraph_supervisor normalizes agent names to lowercase in handoff tools
                    agent_name_map = {
                        "kafka_observability_agent": "Kafka_Observability_Agent",
                        "kubernetes_observability_agent": "Kubernetes_Observability_Agent",
                        "apm_observability_agent": "APM_Observability_Agent",
                        "database_observability_agent": "Database_Observability_Agent",
                        "diagnostic_agent": "Diagnostic_Agent",
                        "code_triage_agent": "Code_Triage_Agent"
                    }

                    # Check if this AIMessage has a name field (orchestrator messages do, sub-agent messages don't)
                    agent_name = msg_data.get("name")

                    if not agent_name:
                        # Sub-agent message - use the currently active agent
                        agent_name = current_active_agent
                    else:
                        # Apply mapping to convert lowercase agent names to proper display names
                        agent_name = agent_name_map.get(agent_name.lower(), agent_name)

                    # Check for handoff tool calls (transfer_to_X) to track which agent becomes active
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "")

                        # Detect handoff to sub-agents
                        if tool_name.startswith("transfer_to_"):
                            # Extract agent name from transfer_to_kafka_observability_agent -> kafka_observability_agent
                            transferred_agent_lowercase = tool_name.replace("transfer_to_", "")
                            # Map to display name: kafka_observability_agent -> Kafka_Observability_Agent
                            transferred_agent = agent_name_map.get(transferred_agent_lowercase,
                                                                   transferred_agent_lowercase)
                            current_active_agent = transferred_agent

                        # Detect handoff back to orchestrator
                        elif tool_name.startswith("transfer_back_to_"):
                            current_active_agent = "Alert_Triage_Orchestrator"

                        # Store tool usage for later attribution
                        tool_usage[tool_call["id"]] = {
                            "agent_name": agent_name,
                            "tool_name": tool_call["name"],
                            "args": tool_call["args"]
                        }

                    if content == "":
                        continue

                    # Special handling for Code Triage Agent: check if previous message was analyze_code tool
                    # If so, truncate the AI's extra analysis and replace with a simple message
                    if agent_name == "Code_Triage_Agent" and len(messages) > 0:
                        # Check if the last message was a ToolMessage from analyze_code
                        last_msg = messages[-1]
                        if (hasattr(last_msg, 'tool_name') and
                            last_msg.tool_name == 'analyze_code' and
                            hasattr(last_msg, 'tool_response') and
                            '[CODE_TRIAGE_COMPLETE]' in (last_msg.tool_response or '')):
                            # This AIMessage is the agent's unwanted analysis after the tool call
                            # Replace it with a simple completion message
                            original_length = len(content)
                            content = "Code analysis complete. See tool execution details above for the full analysis."
                            logger.info(f"Truncated Code_Triage_Agent extra analysis ({original_length} chars removed)")

                    message = TriageAIMessage(
                        agent_name=agent_name,
                        content=content,
                        timestamp=timestamp
                    )

                    messages.append(message)

                elif msg_type == "ToolMessage":

                    # Tool messages
                    # Get tool_call_details first before using it
                    tool_call_details = tool_usage.get(msg_data.get("tool_call_id", ""), dict())

                    # tool_name = msg_data.get("name", "Unknown Tool")
                    tool_name = msg_data.get("name") or tool_call_details.get("tool_name", "Unknown Tool")
                    # Ignore the meta tools that are used by langgraph to indicate agent <-> agent handoffs
                    if tool_name.startswith("transfer_to_") or tool_name.startswith("transfer_back_to_"):
                        continue

                    agent_name = tool_call_details.get("agent_name")

                    if agent_name is None:
                        # If we don't have the agent name, try to get it from the previous AI message
                        # Some issue with LangGraph is causing the AI message to be missing the tool_call_id but
                        # ToolMessage uses it. Either its a LangGraph or Checkpointer issue.
                        # TODO: Check in langgraph repo and see if this is a known issue
                        for item in reversed(messages):
                            if isinstance(item, TriageAIMessage):
                                agent_name = item.agent_name
                                break

                    tool_args = tool_call_details.get("args", "")
                    tool_args = json.dumps(tool_args, indent=2) if isinstance(tool_args, dict) else str(tool_args)

                    # Determine response type based on content
                    response_type = ToolResponseType.TEXT  # Default to text
                    if content:
                        try:
                            json.loads(content)
                            response_type = ToolResponseType.JSON
                        except (json.JSONDecodeError, TypeError):
                            response_type = ToolResponseType.TEXT

                    message = TriageToolMessage(
                        agent_name=agent_name,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_response=content,
                        response_type=response_type,
                        timestamp=timestamp
                    )

                    messages.append(message)

            logger.info(f"Successfully converted {len(messages)} messages for triage journey")

        else:

            logger.info(f"No analysis data found for thread_id: {thread_id}")

    except Exception as e:

        logger.warning(f"Failed to retrieve triage analysis data for thread_id {thread_id}: {e}")

    return messages


def format_root_cause_analysis_content(latest_triage: Optional[TriageDBModel]) -> str:
    """
    Format root cause analysis content based on triage status.

    Args:
        latest_triage: Latest triage record or None if no triage exists

    Returns:
        Formatted markdown content for root cause analysis
    """
    if latest_triage:
        if latest_triage.status == Status.SUCCESS:  # type: ignore
            # Return the actual root cause summary which is already a markdown
            # type: ignore
            return latest_triage.root_cause_summary
        elif latest_triage.status == Status.PENDING:  # type: ignore
            return "**Status:** Analysis pending\n\nThe root cause analysis has not been started yet. Please trigger a manual triage to generate the root cause analysis."
        elif latest_triage.status == Status.QUEUED:  # type: ignore
            return "**Status:** Analysis queued\n\nThe root cause analysis has been queued and will start processing soon. Please check back later."
        elif latest_triage.status == Status.PROCESSING:  # type: ignore
            return "**Status:** Analysis in progress\n\nThe root cause analysis is currently being processed. Please check back later."
        elif latest_triage.status == Status.ERROR:  # type: ignore
            # TODO: check if the error message is retry-able. ( MCP connection issues or model throtelling)
            return f"**Status:** Triage failed\n\nPlease try triggering the analysis again."
        else:
            return "**Status:** Not available\n\nNo root cause analysis is available for this alert."
    else:
        return "**Status:** Not started\n\nNo triage analysis has been performed for this alert yet. Please trigger a manual triage to generate the root cause analysis."


def format_group_root_cause_analysis_content(group, for_individual_alert: bool = True) -> str:
    """
    Format root cause analysis content for an alert group based on triage status.

    Priority order for RCA content:
    1. root_cause_summary (from triage) if triage is completed
    2. Status messages based on triage_status (pending/in_progress/failed)
    3. NOT SHOWING grouping_reasoning anymore - only triage-related content

    Args:
        group: AlertGroupDBModel instance
        for_individual_alert: If True, messages indicate "This alert is part of a group".
                             If False, messages are for the group RCA endpoint directly.

    Returns:
        Formatted markdown content for root cause analysis
    """
    # Priority 1: If triage is completed, show the actual root cause from triage
    if group.triage_status == "completed":
        return group.root_cause_summary or "**Status:** Completed\n\nNo root cause summary available."

    # Priority 2: If triage is in progress, show status message
    if group.triage_status == "in_progress":
        if for_individual_alert:
            return "**Status:** Analysis in progress\n\nThis alert is part of a group. The group triage analysis is currently being processed. Please check back later."
        else:
            return "**Status:** Analysis in progress\n\nThe root cause analysis is currently being processed. Please check back later."

    # Priority 3: If triage failed, show error message
    if group.triage_status == "failed":
        error_msg = f"\n\n**Error:** {group.error_message}" if group.error_message else ""
        if for_individual_alert:
            return f"**Status:** Triage failed\n\nThis alert is part of a group. The group triage analysis failed.{error_msg}\n\nPlease try triggering the analysis again."
        else:
            return f"**Status:** Triage failed\n\nThe triage analysis encountered an error.{error_msg}\n\nPlease check the logs or retry the analysis."

    # Priority 4: If triage is pending, show pending message
    if group.triage_status == "pending":
        if for_individual_alert:
            return "**Status:** Analysis pending\n\nThis alert is part of a group. The group triage analysis has not been started yet."
        else:
            return "**Status:** Analysis pending\n\nThe root cause analysis has not been started yet. Click 'Start Manual Triage' to begin the analysis."

    # Last resort: return not available (no triage status at all)
    if for_individual_alert:
        return "**Status:** Not available\n\nThis alert is part of a group, but no root cause analysis is available."
    else:
        return "**Status:** Not available\n\nNo root cause analysis is available for this alert group."

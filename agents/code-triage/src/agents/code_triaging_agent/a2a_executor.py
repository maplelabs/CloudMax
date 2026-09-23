"""A2A AgentExecutor wrapper for the Code Triaging workflow.

This module adapts the existing LangGraph-based CodeTriagingAgent into the
standard A2A server execution model. It exposes a single skill via the
"message/send" method: triaging code errors for a given repository.
"""

from __future__ import annotations

import logging
import re
from typing import Tuple

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Artifact, DataPart
from a2a.utils.message import get_message_text
from a2a.utils.parts import get_data_parts
from a2a.utils.task import completed_task

from src.agents.code_triaging_agent import CodeTriagingAgent


logger = logging.getLogger(__name__)


# Input validation limits for triage requests.
# These are conservative bounds to prevent extremely large payloads from
# reaching the LangGraph workflow and downstream LLM calls.
MAX_ERROR_LENGTH = 50_000  # ~50 KB of error/stack trace text
MAX_REPOSITORY_NAME_LENGTH = 100


def _validate_triage_inputs(error: str, repository: str) -> None:
	"""Validate input sizes and repository format for triage requests.

	Raises ValueError when inputs are outside acceptable bounds so that the
	A2A executor can surface a clear "Invalid request" error to callers.
	"""
	if len(error) > MAX_ERROR_LENGTH:
		raise ValueError(
			f"Error message too large: {len(error)} chars > {MAX_ERROR_LENGTH} chars"
		)

	if len(repository) > MAX_REPOSITORY_NAME_LENGTH:
		raise ValueError(
			f"Repository name too long: {len(repository)} > {MAX_REPOSITORY_NAME_LENGTH}"
		)

	if not re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$", repository):
		raise ValueError(
			f"Invalid repository format: {repository}. Expected 'owner/repo'."
		)


class CodeTriagerAgentExecutor(AgentExecutor):
	"""AgentExecutor that runs the code triage workflow for A2A.

	This executor expects an incoming A2A Message whose content includes a
	structured payload describing the triage request. The recommended format
	is a DataPart with the following JSON structure:

	    {"error": "...stack trace...", "repository": "owner/repo"}

	If no DataPart is present, the executor falls back to using the combined
	text content of the message as the error string, and requires a
	"repository" field in at least one DataPart.
	"""

	def __init__(self) -> None:
		# Reuse the existing LangGraph-based orchestrator. We *do not* start
		# its legacy HTTP server; we only use its triage workflow.
		self._agent = CodeTriagingAgent()

	def _extract_triage_inputs(self, context: RequestContext) -> Tuple[str, str]:
		"""Extract (error, repository) from the incoming A2A Message.

		Prefers DataPart payloads with keys "error" and "repository". If
		error is not found in a DataPart, falls back to using the concatenated
		text content of the message as the error string.
		"""

		if context.message is None:
			raise ValueError("A2A RequestContext.message is required for triage")

		msg = context.message

		error: str | None = None
		repository: str | None = None

		# First, look for structured data parts
		for data in get_data_parts(msg.parts or []):
			if isinstance(data, dict):
				if "error" in data and not error:
					error = data.get("error")
				if "repository" in data and not repository:
					repository = data.get("repository")

		# Fallback: use full text content as error string if not provided
		if not error:
			error_text = get_message_text(msg).strip()
			if error_text:
				error = error_text

		if not error:
			raise ValueError("Triage request is missing 'error' content")
		if not repository:
			raise ValueError("Triage request is missing 'repository' field")

		return error, repository

	async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
		"""Run the triage workflow and publish a completed Task event.

		The resulting Task contains a single Artifact with a DataPart whose
		"data" field is the structured triage report dict.
		"""

		try:
			error, repository = self._extract_triage_inputs(context)
			# Validate input size and format before running the workflow.
			_validate_triage_inputs(error, repository)
			logger.info(
				"Executing triage via A2A executor for repo=%s, task_id=%s",
				repository,
				getattr(context, "task_id", "<unknown>"),
			)

			# Run the core triage workflow using the async LangGraph API
			report = await self._agent._run_triage_workflow_async(  # type: ignore[attr-defined]
				error=error,
				repository=repository,
			)

			# Wrap the report in a DataPart inside an Artifact
			data_part = DataPart(data=report)
			artifact = Artifact(
				artifactId="triage-result",
				name="triage_result",
				description="Code triage report",
				parts=[data_part],
			)

			# Build a completed Task representing this triage run
			task = completed_task(
				context_id=context.context_id,
				task_id=context.task_id,
				artifacts=[artifact],
				history=None,
			)

			# Enqueue the Task as an event so the server can stream or return it
			await event_queue.enqueue_event(task)

		except ValueError as e:
			# Input validation errors - user's fault (e.g., invalid repo format)
			logger.warning("Invalid triage request: %s", e)
			raise ValueError(f"Invalid request: {e}") from e

		except RuntimeError as e:
			# Expected runtime errors with user-friendly messages
			# (e.g., LLM rate limit, auth failure, timeout)
			logger.error("Triage execution failed: %s", e)
			raise  # Already has good error message from workflow

		except Exception as e:  # pragma: no cover - defensive logging
			# Unexpected errors - log with full context and provide generic message
			logger.error("Unexpected error in triage executor: %s", e, exc_info=True)
			raise RuntimeError(f"Internal error: {type(e).__name__}: {str(e)}") from e

	async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
		"""Best-effort cancellation hook.

		The current triage workflow is short-lived and synchronous, so there
		is no fine-grained cancellation. This method is implemented to comply
		with the AgentExecutor interface and can be extended later if needed.
		"""

		logger.info(
			"Received cancel request for task_id=%s (no-op for current workflow)",
			getattr(context, "task_id", "<unknown>"),
		)

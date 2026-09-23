"""A2A Client for Code Triage Service."""

import asyncio
import httpx
import logging
import uuid
from typing import Dict, Any

from .models import CodeTriageResponse

logger = logging.getLogger(__name__)


class CodeTriageA2AClient:
    """Client for communicating with code-triage service via A2A protocol."""

    def __init__(self, base_url: str, timeout: int = 180, max_retries: int = 3) -> None:
        """Initialize the A2A client.

        Args:
            base_url: Base URL of the code-triage service.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for transient errors.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def analyze_code(
        self,
        error: str,
        repository: str,
    ) -> CodeTriageResponse:
        """Send an A2A request to the code-triage service.

        Implements retry logic with exponential backoff for *retryable* failures
        (HTTP 429/5xx, timeouts) and fails fast on client errors (HTTP 400/401/403/404).
        """

        # Build A2A JSON-RPC request
        request_id = str(uuid.uuid4())
        a2a_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": request_id,
                    "role": "user",
                    "parts": [
                        {
                            "kind": "data",
                            "data": {
                                "error": error,
                                "repository": repository,
                            },
                        }
                    ],
                }
            },
        }

        # Try with retries and exponential backoff for *retryable* failures only
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.info(
                        "Calling code-triage service at %s (attempt %d/%d)",
                        self.base_url,
                        attempt + 1,
                        self.max_retries,
                    )

                    # Log the A2A request being sent
                    import json
                    logger.info("=" * 80)
                    logger.info("A2A REQUEST to code-triage-agent:")
                    logger.info(json.dumps(a2a_request, indent=2))
                    logger.info("=" * 80)

                    response = await client.post(
                        f"{self.base_url}/a2a/tasks",
                        json=a2a_request,
                    )

                status = response.status_code

                # Successful response
                if status == 200:
                    data = response.json()

                    # Log the A2A response received
                    import json
                    logger.info("=" * 80)
                    logger.info("A2A RESPONSE from code-triage-agent:")
                    logger.info(json.dumps(data, indent=2))
                    logger.info("=" * 80)

                    logger.info("Code-triage service returned successful response")
                    return self._parse_response(data)

                # Non-retryable client errors – fail fast
                if status in (400, 401, 403, 404):
                    logger.error(
                        "Non-retryable error from code-triage service: HTTP %s - %s",
                        status,
                        response.text[:200],
                    )
                    return CodeTriageResponse(
                        status="error",
                        root_cause=(
                            f"Request to code-triage service failed: HTTP {status}"
                        ),
                    )

                # Retryable server / throttling errors
                if status in (429, 500, 502, 503):
                    logger.warning(
                        "Retryable error from code-triage service: HTTP %s - %s",
                        status,
                        response.text[:200],
                    )
                    if attempt < self.max_retries - 1:
                        # Exponential backoff: 1s, 2s, 4s, ...
                        backoff = 2**attempt
                        await asyncio.sleep(backoff)
                        continue
                    return CodeTriageResponse(
                        status="error",
                        root_cause=(
                            "Code-triage service unavailable after "
                            f"{self.max_retries} attempts (last HTTP {status})"
                        ),
                    )

                # Any other unexpected status: treat as non-retryable
                logger.error(
                    "Unexpected non-retryable status from code-triage service: "
                    "HTTP %s - %s",
                    status,
                    response.text[:200],
                )
                return CodeTriageResponse(
                    status="error",
                    root_cause=(
                        f"Unexpected response from code-triage service: HTTP {status}"
                    ),
                )

            except httpx.TimeoutException:
                logger.warning(
                    "Timeout calling code-triage service on attempt %d/%d",
                    attempt + 1,
                    self.max_retries,
                )
                if attempt < self.max_retries - 1:
                    backoff = 2**attempt
                    await asyncio.sleep(backoff)
                    continue
                return CodeTriageResponse(
                    status="timeout",
                    root_cause=(
                        "Code analysis timed out after "
                        f"{self.max_retries} attempts"
                    ),
                )

            except Exception as e:
                logger.error(
                    "Error calling code-triage service on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                    exc_info=True,
                )
                if attempt < self.max_retries - 1:
                    backoff = 2**attempt
                    await asyncio.sleep(backoff)
                    continue
                return CodeTriageResponse(
                    status="error",
                    root_cause=(
                        "Code analysis failed after "
                        f"{self.max_retries} attempts: {e}"
                    ),
                )

        # Should not be reached, but keep a defensive fallback.
        return CodeTriageResponse(
            status="error",
            root_cause="Code analysis failed after all retry attempts",
        )

    def _parse_response(self, data: Dict[str, Any]) -> CodeTriageResponse:
        """Parse A2A JSON-RPC response into ``CodeTriageResponse``.

        The code-triage-agent follows JSON-RPC 2.0 semantics. A successful
        call returns a ``result`` field, while failures return an ``error``
        object. We surface JSON-RPC errors as ``status='error'`` so callers
        can distinguish transport/validation failures from successful
        code-analysis responses.

        Args:
            data: Raw JSON response body from the A2A endpoint.

        Returns:
            Parsed ``CodeTriageResponse`` instance.
        """

        # If the server returned a JSON-RPC error, surface it directly.
        if "error" in data:
            error_obj = data.get("error", {}) or {}
            message = error_obj.get("message", "Unknown error from code-triage service")
            logger.error(f"Code-triage service returned JSON-RPC error: {message}")
            return CodeTriageResponse(
                status="error",
                root_cause=message,
                code_snippets=[],
                suggested_fixes=[],
                confidence=0.0,
            )

        # Normal successful JSON-RPC response with a ``result`` payload.
        result = data.get("result", {}) or {}

        if not isinstance(result, dict):
            logger.error(f"Unexpected A2A result type: {type(result)}")
            return CodeTriageResponse(
                status="error",
                root_cause="Invalid result format from code-triage service",
                code_snippets=[],
                suggested_fixes=[],
                confidence=0.0,
            )

        # The code-triage-agent wraps the triage report dict inside a Task
        # artifact named "triage_result". The structure is roughly:
        # {
        #   "result": {
        #     "state": "completed",
        #     "artifacts": [
        #       {
        #         "artifactId": "triage-result",
        #         "name": "triage_result",
        #         "parts": [{"data": { ... triage report ... }}]
        #       }
        #     ]
        #   }
        # }
        report: Dict[str, Any] | None = None

        artifacts = result.get("artifacts") or []
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                if artifact.get("artifactId") == "triage-result" or artifact.get("name") == "triage_result":
                    parts = artifact.get("parts") or []
                    for part in parts:
                        if isinstance(part, dict) and "data" in part:
                            data_part = part.get("data") or {}
                            if isinstance(data_part, dict):
                                report = data_part
                                break
                    if report is not None:
                        break

        # Fallback: in case older versions returned the report at top level
        if report is None and any(
            key in result for key in ("root_cause", "code_snippets", "recommendations", "suggested_fixes")
        ):
            report = result

        if report is None:
            logger.error("Code-triage service result did not contain a triage report artifact")
            return CodeTriageResponse(
                status="error",
                root_cause="No triage report found in code-triage service result",
                code_snippets=[],
                suggested_fixes=[],
                confidence=0.0,
            )

        # Map the inner triage report dict (TriageState final output) to
        # our CodeTriageResponse model.
        status_val = report.get("status")
        if not isinstance(status_val, str):
            # Fallback to Task-level state if present
            state = result.get("state")
            status_val = state if isinstance(state, str) else "completed"

        root_cause = report.get("root_cause")

        code_snippets = report.get("code_snippets") or []
        if not isinstance(code_snippets, list):
            code_snippets = []

        suggested = report.get("suggested_fixes")
        if suggested is None:
            suggested = report.get("recommendations") or []
        if not isinstance(suggested, list):
            suggested = []

        confidence_val = report.get("confidence")
        try:
            confidence_f = float(confidence_val) if confidence_val is not None else 0.0
        except (TypeError, ValueError):
            confidence_f = 0.0

        return CodeTriageResponse(
            status=status_val,
            root_cause=root_cause,
            code_snippets=code_snippets,
            suggested_fixes=suggested,
            confidence=confidence_f,
        )


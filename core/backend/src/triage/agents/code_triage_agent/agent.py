"""
Code Triage Agent

Wrapper/Adapter agent that integrates with remote code-triage service.
"""

import logging

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.triage.agents.abstract_agent import AbstractAgent
from .client import CodeTriageA2AClient
from .prompts import CODE_ANALYSIS_REJECTION_TEMPLATE

logger = logging.getLogger(__name__)


class AnalyzeCodeInput(BaseModel):
    """Input schema for analyze_code tool"""
    error: str = Field(description="Error message to analyze")
    repository: str = Field(description="GitHub repository in format owner/repo")


class CodeTriageAgent(AbstractAgent):
    """Code Triage Agent that analyzes application code to identify root causes.

    This agent is a thin wrapper/adapter around the remote code-triage service:

    1. Initializes an A2A client using centralized configuration.
    2. Exposes an `analyze_code` tool that accepts an error message and a GitHub
       repository identifier in the form `owner/repo`.
    3. Forwards requests to the code-triage-agent service via the A2A HTTP API.
    4. Returns a human-readable summary of the triage result for use by the
       orchestrator and other agents.

    Note:
        Extraction of the repository and error from alerts, runbooks, and
        conversation context happens in the orchestrator workflow, not inside
        this agent. This agent assumes both `error` and `repository` are
        provided explicitly as tool arguments.
    """
    
    def __init__(self):
        """
        Initialize Code Triage Agent.

        Note:
            GitHub token is configured via environment variable in the
            code-triage-agent service, not passed from this agent.
        """
        super().__init__()
        self.base_url: str = ""
        self.client: CodeTriageA2AClient = None

    async def _async_init(self, workflow_mode: str = "orchestrator", **kwargs):
        """
        Async initialization of Code Triage Agent.

        Args:
            workflow_mode: Workflow mode (default: "orchestrator")
        """
        # Call parent async init to set up LLM
        await super()._async_init(workflow_mode=workflow_mode, **kwargs)

        # Get code-triage configuration
        from src.server.utilities.code_triage_config import get_code_triage_config

        config = await get_code_triage_config()

        if not config:
            raise ValueError("Code triage configuration not found or disabled")

        # Set configuration
        self.base_url = config.base_url
        self.client = CodeTriageA2AClient(config.base_url, config.timeout_seconds, config.max_retries)

        logger.info(f"Code Triage Agent initialized (base_url: {config.base_url})")

    def _is_code_analyzable_error(self, error: str) -> tuple[bool, str]:
        """Basic pre-flight check. Detailed classification happens in Error Parser Agent."""
        error_clean = error.strip()

        if len(error_clean) < 20:
            return False, "Error message too short"

        if not any(c.isalnum() for c in error_clean):
            return False, "Error message contains no meaningful content"

        if len(error_clean) > 100000:
            return False, "Error message exceeds reasonable length"

        return True, "Basic validation passed"

    def _create_analyze_tool(self) -> StructuredTool:
        """
        Create tool that calls A2A client to analyze code.

        Returns:
            StructuredTool: Tool for code analysis
        """
        async def analyze_code_impl(error: str, repository: str) -> str:
            """Analyze code for an error in a given GitHub repository.

            Args:
                error: Error message to analyze.
                repository: GitHub repository in the format "owner/repo".

            Returns:
                A human-readable analysis summary string.
            """

            try:
                # PRE-FLIGHT VALIDATION: Check if error is code-analyzable
                is_valid, reason = self._is_code_analyzable_error(error)

                if not is_valid:
                    logger.warning(
                        f"❌ Rejecting code analysis request for repository: {repository}"
                    )
                    logger.warning(f"   Reason: {reason}")
                    logger.warning(f"   Error preview: {error[:200]}...")

                    rejection_msg = CODE_ANALYSIS_REJECTION_TEMPLATE.format(reason=reason)
                    # Add termination marker
                    return rejection_msg + "\n\n[CODE_TRIAGE_COMPLETE]"

                logger.info(f"✅ Pre-flight validation passed: {reason}")
                logger.info(f"🔍 Calling A2A client for repository: {repository}")
                response = await self.client.analyze_code(error, repository)

                # Check if analysis completed successfully
                if not response.is_success():
                    status = response.status or "unknown"
                    reason = response.root_cause or "No details provided."
                    logger.warning(
                        "Code triage A2A call did not complete successfully "
                        "(status=%s): %s",
                        status,
                        reason,
                    )
                    failure_msg = (
                        "⚠️ Code Triage Sub-Agent FAILED\n"
                        f"Status: {status}\n"
                        f"Details: {reason}\n"
                    )
                    # Add termination marker
                    return failure_msg + "\n[CODE_TRIAGE_COMPLETE]"

                logger.info(f"✅ A2A client returned analysis for {repository}")

                # Format the response properly for successful analysis
                result = f"""Code Analysis Results:

Repository: {repository}
Status: {response.status}

Root Cause:
{response.root_cause or 'Not identified'}

"""

                # Add code snippets if available
                if response.code_snippets:
                    result += f"Code Snippets Found: {len(response.code_snippets)}\n"
                    for i, snippet in enumerate(response.code_snippets[:3], 1):  # Limit to 3
                        # Handle both Pydantic CodeSnippet models and dicts for robustness
                        if isinstance(snippet, dict):
                            file_path = snippet.get("file_path", "unknown")
                            content = snippet.get("content", "")
                        else:
                            # Pydantic CodeSnippet model (normal case)
                            file_path = getattr(snippet, "file_path", "unknown")
                            content = getattr(snippet, "content", "")

                        result += f"\n{i}. {file_path}\n"
                        if content:
                            # Show first 200 chars of content
                            result += f"   {content[:200]}...\n"

                # Add suggested fixes if available
                if response.suggested_fixes:
                    result += "\nSuggested Fixes:\n"
                    for i, fix in enumerate(response.suggested_fixes, 1):
                        result += f"{i}. {fix}\n"

                # Add confidence score
                result += f"\nConfidence: {int(response.confidence * 100)}%"

                # Add termination marker to signal completion
                result += "\n\n[CODE_TRIAGE_COMPLETE]"

                return result

            except httpx.ConnectError as e:
                # Surface transport-level failures to the orchestrator instead of
                # hiding them inside a string. This allows higher-level workflows
                # to differentiate between "no triage result" and "service down".
                raise RuntimeError(
                    f"Code-triage service unreachable at {self.base_url}"
                ) from e
            except httpx.TimeoutException as e:
                raise RuntimeError(
                    f"Code-triage service timeout after {self.client.timeout}s"
                ) from e
            except Exception as e:
                logger.error(f"A2A call failed: {e}", exc_info=True)
                raise RuntimeError(
                    f"Code analysis failed: {type(e).__name__}: {str(e)}"
                ) from e

        return StructuredTool(
            name="analyze_code",
            description="Analyze application code to identify root cause of errors. Requires error message and GitHub repository.",
            func=analyze_code_impl,
            args_schema=AnalyzeCodeInput,
            coroutine=analyze_code_impl  # For async execution
        )

    def get_agent_name(self) -> str:
        """Get agent name for identification"""
        return "Code_Triage_Agent"

    async def get_mcp_config(self) -> dict:
        """
        Get MCP configuration for this agent.
        Code-triage-agent doesn't use MCP servers directly.
        """
        return {}

    def get_prompt(self) -> str:
        """
        Get the prompt for this agent.
        Code-triage-agent uses its own internal prompts for repository extraction.
        """
        return """You are a simple tool-calling proxy. Your ONLY purpose is to call a tool and stop.

INSTRUCTIONS:
1. Call analyze_code tool immediately with the error and repository
2. The tool will return a COMPLETE analysis - DO NOT add anything to it
3. STOP immediately after the tool returns

The analyze_code tool provides a FINAL, COMPLETE response that requires NO additional processing from you.

DO NOT:
- Add commentary after the tool returns
- Write "Based on the analysis..."
- Create your own "ROOT CAUSE ANALYSIS REPORT"
- Add recommendations or conclusions
- Interpret or summarize the tool output

Just call the tool and let its response be the final answer."""

    def get_tools_needed(self) -> list:
        """
        Get tools needed by this agent.
        Returns the analyze_code tool that calls the A2A client.
        """
        return [self._create_analyze_tool()]

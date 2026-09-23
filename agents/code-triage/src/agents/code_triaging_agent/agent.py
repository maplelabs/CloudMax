"""Code Triaging Agent - Main orchestrator with LLM-based routing"""

import asyncio
import json
import logging
from typing import Dict, Any, Literal, List

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from src.state import TriageState
from src.llm_client import get_llm
from src.mcp_tools import (
    GitHubMCPTools,
    MCPToolNotInitializedError,
    MCPAuthenticationError,
    MCPTimeoutError,
    MCPHTTPError,
    extract_relevant_lines,
)
from src.agents.middlewares import TokenCountingCallback, GlobalTokenTracker
from .prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    SHOULD_RETRIEVE_CODE_PROMPT,
    EVALUATE_RETRIEVAL_PROMPT,
    SHOULD_REFINE_ANALYSIS_PROMPT,
)
from src.agents.error_parser_agent.agent import (
    ErrorParseResult,
    parse_error_with_agent,
)
from src.agents.code_retrieval_agent.agent import (
    CodeRetrievalResult,
    plan_code_retrieval_from_state,
)
from src.agents.code_analyzer_agent.agent import (
    CodeAnalysisResult,
    analyze_with_agent,
)

logger = logging.getLogger(__name__)

# Constants for code context validation and confidence adjustment
MIN_CODE_CONTENT_LENGTH = 50
HIGH_CONFIDENCE_THRESHOLD = 0.75
GENERIC_RESPONSE_CONFIDENCE = 0.1
NO_CODE_CONFIDENCE_MULTIPLIER = 0.6
MAX_NO_CODE_CONFIDENCE = 0.6
MIN_ROOT_CAUSE_LENGTH = 20


def _parse_repository(repository: str) -> tuple[str, str]:
    """Parse and validate repository format.

    Args:
        repository: Repository in format "owner/repo"

    Returns:
        Tuple of (owner, repo)

    Raises:
        ValueError: If repository format is invalid
    """
    parts = repository.split("/")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid repository format: {repository}. Expected 'owner/repo'."
        )
    return parts[0], parts[1]


def _is_infrastructure_error(error: Exception, keywords: List[str]) -> bool:
    """Check if error message contains infrastructure-related keywords."""
    error_msg = str(error).lower()
    return any(keyword in error_msg for keyword in keywords)


def _raise_llm_infrastructure_error(error: Exception, context: str) -> None:
    """Detect LLM infrastructure errors and raise with clear, actionable messages.

    Args:
        error: The caught exception
        context: Description of what operation failed (e.g., "Error parser", "Code analyzer")

    Raises:
        RuntimeError: With user-friendly message based on error type
    """
    if _is_infrastructure_error(error, ["rate", "limit"]):
        raise RuntimeError(f"{context}: LLM rate limit exceeded - please retry later") from error
    elif _is_infrastructure_error(error, ["auth", "credential", "unauthorized"]):
        raise RuntimeError(f"{context}: LLM authentication failed - check BEDROCK_API_KEY") from error
    elif _is_infrastructure_error(error, ["timeout", "timed out"]):
        raise RuntimeError(f"{context}: LLM service timeout - please retry") from error
    else:
        raise RuntimeError(f"{context} failed: {str(error)}") from error


def _extract_json_text_from_response(response) -> str:
    """Normalize an LLM JSON response, stripping markdown code fences.

    Many models return JSON wrapped in ``` or ```json fences. This helper
    removes those wrappers so the result can be safely passed to json.loads.
    """

    json_text = response.content.strip()
    if json_text.startswith("```"):
        # Take the inner fenced block between the first pair of ``` markers.
        # Note: split without maxsplit so that trailing fences are discarded.
        parts = json_text.split("```")
        if len(parts) > 1:
            json_text = parts[1]
        # Optional leading language tag like "json"
        if json_text.startswith("json"):
            json_text = json_text[4:]
    return json_text.strip()


class CodeTriagingAgent:
    """Main code triaging agent with LLM-based routing.

    This class is now transport-agnostic and no longer inherits from the
    legacy HTTP A2AServer base class. All server concerns are handled by the
    a2a-sdk FastAPI integration in src.a2a_app.
    """

    def __init__(self):
        super().__init__()

        # Get LLM for routing decisions
        self.routing_llm = get_llm(temperature=0.1, max_tokens=500)

        # Token counting callback for routing LLM
        self.token_callback = TokenCountingCallback(name="orchestrator_routing")

        # Create main workflow with LLM-based routing
        self.workflow = self._create_workflow()

        logger.info("Initialized CodeTriagingAgent with LLM-based routing")
    
    def _create_workflow(self):
        """Create main LangGraph workflow with conditional routing"""
        workflow = StateGraph(TriageState)
        
        # Add nodes
        workflow.add_node("parse_error", self._run_error_parser)
        workflow.add_node("decide_retrieval", self._decide_code_retrieval)
        workflow.add_node("retrieve_code", self._run_code_retrieval)
        workflow.add_node("evaluate_retrieval", self._evaluate_retrieval)
        workflow.add_node("analyze_code", self._run_code_analyzer)
        workflow.add_node("evaluate_analysis", self._evaluate_analysis)
        workflow.add_node("generate_report", self._generate_report)
        
        # Define workflow with conditional edges
        workflow.set_entry_point("parse_error")
        
        # After parsing, decide if we need code
        workflow.add_edge("parse_error", "decide_retrieval")
        
        # Conditional: Should we retrieve code?
        workflow.add_conditional_edges(
            "decide_retrieval",
            self._route_after_retrieval_decision,
            {
                "retrieve": "retrieve_code",
                "skip": "analyze_code"
            }
        )
        
        # After retrieval, evaluate success
        workflow.add_edge("retrieve_code", "evaluate_retrieval")
        
        # Conditional: Was retrieval successful?
        workflow.add_conditional_edges(
            "evaluate_retrieval",
            self._route_after_retrieval_evaluation,
            {
                "proceed": "analyze_code",
                "retry": "retrieve_code",
                "skip": "analyze_code"
            }
        )
        
        # After analysis, evaluate quality
        workflow.add_edge("analyze_code", "evaluate_analysis")
        
        # Conditional: Is analysis good enough?
        workflow.add_conditional_edges(
            "evaluate_analysis",
            self._route_after_analysis_evaluation,
            {
                "accept": "generate_report",
                "refine": "analyze_code",
                "more_code": "retrieve_code"
            }
        )
        
        # Final report leads to end
        workflow.add_edge("generate_report", END)
        
        return workflow.compile()
    
    # SUBAGENT EXECUTION NODES 
    
    async def _run_error_parser(self, state: TriageState) -> Dict:
        """Parse error message and stack trace via the error parser subagent.

        Also validates repository format and accessibility before proceeding.
        """
        logger.info("Error Parser: Parsing error via subagent...")

        # Validate repository first - fail fast if invalid
        # Step 1: Validate format (owner/repo)
        try:
            owner, repo = _parse_repository(state["repository"])
        except ValueError as e:
            logger.error("Repository validation failed: %s", e)
            raise  # Re-raise to fail fast

        # Step 2: Validate accessibility (GitHub API check)
        from src.mcp_tools import validate_github_repository
        from src.config import GITHUB_TOKEN

        repo_valid, repo_error = await validate_github_repository(owner, repo, GITHUB_TOKEN)

        if not repo_valid:
            logger.error("Repository validation failed: %s", repo_error)
            # Fail fast - don't waste LLM calls on inaccessible repo
            raise ValueError(f"Repository validation failed: {repo_error}")

        try:
            # Run the LLM error parser subagent
            result: ErrorParseResult = parse_error_with_agent(
                error_message=state["error_message"],
                stack_trace=state["stack_trace"],
            )

            logger.info("Parsed error type: %s", result.error_type)
            logger.info(
                "Parsed language=%s, severity=%s, needs_code=%s",
                result.language,
                result.severity,
                result.needs_code,
            )

            # Use only the LLM-provided file hints; no regex or path cleaning.
            llm_file_hints = result.file_hints or []

            if llm_file_hints:
                logger.info("Using file hints from LLM: %s", llm_file_hints)
            else:
                logger.info(
                    "No file hints from LLM; retrieval will rely on search strategy: %s",
                    result.search_strategy,
                )

            # Update state fragment
            return {
                "error_type": result.error_type,
                "language": result.language,
                "file_hints": llm_file_hints,
                "line_hints": result.line_hints,
                "search_strategy": result.search_strategy,
                "needs_code": result.needs_code,
                "severity": result.severity,
            }
        except Exception as e:  # pragma: no cover - defensive
            # Don't hide infrastructure errors - fail fast with clear message
            logger.error("Error parser LLM failed: %s", e, exc_info=True)
            _raise_llm_infrastructure_error(e, "Error parser")
            raise  # This line is never reached but satisfies static analyzers

    async def _run_code_retrieval(self, state: TriageState) -> Dict:
        """Retrieve code from GitHub using MCP tools (async).

        This inlines the previous code_retrieval subgraph logic while keeping
        the same behaviour and state updates.
        """
        # Compute the next attempt number up front so we can log it clearly.
        attempt_count = state.get("retrieval_attempt_count", 0) + 1
        logger.info(
            "Code Retrieval: Fetching code (attempt=%d) for repo=%s",
            attempt_count,
            state.get("repository", "<unknown>"),
        )

        try:
            # Initialize MCP tools (async-backed client)
            mcp_tools = GitHubMCPTools()

            # Repository format and accessibility already validated in _run_error_parser()
            # Workflow guarantees we only reach here with a valid repository
            repository = state["repository"]
            owner, repo = repository.split("/")  # Safe - already validated

            snippets: List[Dict] = []

            # Use a LangChain agent to plan retrieval strategy (file paths vs search)
            plan: CodeRetrievalResult | None = None
            try:
                plan = plan_code_retrieval_from_state(state)
                logger.info(
                    "Retrieval plan: strategy=%s, file_hints=%s, queries=%s",
                    plan.retrieval_strategy,
                    plan.file_hints,
                    plan.search_queries,
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "Code retrieval planning agent failed, using fallback: %s", e
                )

            # Strategy 1: Try to fetch from planned/known file paths first,
            # optionally augmented with hints suggested by the analyzer.
            file_hints = state.get("file_hints", []) or []
            if plan and plan.file_hints:
                file_hints = plan.file_hints

            analysis_hints = state.get("analysis_additional_file_hints") or []

            # Merge and deduplicate hints while preserving order
            merged_hints: List[str] = []
            for hint in list(file_hints) + list(analysis_hints):
                if hint and hint not in merged_hints:
                    merged_hints.append(hint)
            file_hints = merged_hints

            if file_hints:
                logger.info("Fetching %d file hints", len(file_hints))

                # Track failed file retrievals for transparency
                failed_files = []

                # Get line hints for extracting relevant sections
                line_hints = state.get("line_hints", []) or []

                for idx, file_hint in enumerate(file_hints):
                    try:
                        result = await mcp_tools.get_file_contents(owner, repo, file_hint)

                        if result is not None:
                            # Extract relevant lines if we have line number for this file
                            snippet_metadata = {}
                            if idx < len(line_hints) and line_hints[idx]:
                                # Convert line number from string to int (LLM returns strings)
                                try:
                                    line_number = int(line_hints[idx])
                                    logger.info(
                                        "Extracting relevant lines around line %d from %s",
                                        line_number,
                                        file_hint,
                                    )
                                    result, snippet_metadata = extract_relevant_lines(
                                        result,
                                        line_number,
                                        context_lines=50
                                    )
                                except (ValueError, TypeError) as e:
                                    logger.warning(
                                        "Invalid line number '%s' for %s, using full file: %s",
                                        line_hints[idx],
                                        file_hint,
                                        e,
                                    )

                            snippets.append(
                                {
                                    "file_path": file_hint,
                                    "content": result,
                                    "language": state.get("language", "python"),
                                    **snippet_metadata,  # Include extraction metadata if present
                                }
                            )
                            logger.info("Fetched %s", file_hint)
                        else:
                            # result is None - file not found (404)
                            failed_files.append((file_hint, "File not found"))
                            logger.info("File not found: %s", file_hint)

                    except MCPAuthenticationError as e:
                        # Critical: authentication failed - log error and stop retrieval
                        failed_files.append((file_hint, f"Authentication failed: {str(e)}"))
                        logger.error(
                            "Authentication failed while fetching %s: %s - stopping retrieval",
                            file_hint,
                            e,
                        )
                        # Re-raise to fail fast on auth errors
                        raise

                    except MCPTimeoutError as e:
                        # Timeout - log warning and continue with other files
                        failed_files.append((file_hint, f"Timeout: {str(e)}"))
                        logger.warning(
                            "Timeout fetching %s: %s - continuing with other files",
                            file_hint,
                            e,
                        )

                    except MCPHTTPError as e:
                        # HTTP error (rate limiting, server error, etc.)
                        if e.status_code == 429:
                            failed_files.append((file_hint, "Rate limited"))
                            logger.warning(
                                "Rate limited while fetching %s - stopping retrieval to avoid further rate limiting",
                                file_hint,
                            )
                            # Stop retrieval on rate limiting to avoid making it worse
                            break
                        else:
                            failed_files.append((file_hint, f"HTTP {e.status_code}: {str(e)}"))
                            logger.warning(
                                "HTTP %d error fetching %s: %s - continuing with other files",
                                e.status_code,
                                file_hint,
                                e,
                            )

                    except MCPToolNotInitializedError as e:
                        # Critical setup error - log and re-raise
                        failed_files.append((file_hint, f"Tool not initialized: {str(e)}"))
                        logger.error(
                            "MCP tool not initialized: %s - this should not happen",
                            e,
                        )
                        raise

                    except Exception as e:
                        # Unexpected error - log with traceback and continue
                        failed_files.append((file_hint, f"Unexpected error: {str(e)}"))
                        logger.warning(
                            "Unexpected error fetching %s: %s",
                            file_hint,
                            e,
                            exc_info=True,
                        )

                # Log summary of retrieval results
                if failed_files:
                    logger.warning(
                        "Failed to retrieve %d/%d files: %s",
                        len(failed_files),
                        len(file_hints),
                        failed_files,
                    )

        except MCPAuthenticationError as e:  # pragma: no cover - defensive
            # Authentication failures are critical infrastructure issues and should
            # fail the workflow fast with a clear message instead of silently
            # dropping all code context.
            raise RuntimeError("GitHub authentication failed - check GITHUB_TOKEN") from e
        except MCPToolNotInitializedError as e:  # pragma: no cover - defensive
            # MCP tool setup failures indicate a configuration or startup bug.
            raise RuntimeError("MCP tool initialization failed") from e
        except Exception as e:  # pragma: no cover - defensive
            # Any other unexpected error during retrieval is surfaced to the
            # orchestrator rather than continuing with empty snippets.
            logger.error(f"Code retrieval failed: {e}", exc_info=True)
            raise RuntimeError(
                f"Code retrieval failed: {type(e).__name__}: {str(e)}"
            ) from e

        # Combine code content with file headers
        formatted_snippets = []
        for s in snippets:
            file_path = s.get("file_path", "unknown")
            content = s.get("content", "")
            line_range = s.get("line_range", "")

            # Format with clear file header
            header = f"### File: {file_path}"
            if line_range:
                header += f" (lines {line_range})"
            header += " ###"

            formatted_snippets.append(f"{header}\n\n{content}")

        code_content = "\n\n---\n\n".join(formatted_snippets)

        logger.info(
            "Retrieved %d code snippets (%d chars)",
            len(snippets),
            len(code_content),
        )

        return {
            "code_snippets": snippets,
            "code_content": code_content,
            "retrieval_attempt_count": attempt_count,
            "retrieval_failures": failed_files if 'failed_files' in locals() else [],
        }

    def _run_code_analyzer(self, state: TriageState) -> Dict:
        """Analyze code and identify root cause via the code analyzer subagent."""
        logger.info("Code Analyzer: Analyzing code via subagent...")

        # Increment analysis counter
        attempt_count = state.get("analysis_attempt_count", 0) + 1

        try:
            code_content = state.get("code_content", "No code context available")
            result: CodeAnalysisResult = analyze_with_agent(
                error_message=state["error_message"],
                stack_trace=state["stack_trace"],
                code_content=code_content,
            )

            logger.info(
                "Analysis confidence: %.2f, root_cause_preview=%s",
                result.confidence,
                (result.root_cause or "")[:120],
            )

            return {
                "root_cause": result.root_cause,
                "affected_code": result.affected_code,
                "recommendations": result.recommendations,
                "confidence": result.confidence,
                "analysis_attempt_count": attempt_count,
                "analysis_needs_more_code": result.needs_more_code,
                "analysis_additional_file_hints": result.additional_file_hints,
                "analysis_is_specific": result.analysis_is_specific,
                "code_references_count": result.code_references_count,
            }
        except Exception as e:  # pragma: no cover - defensive
            # Don't hide infrastructure errors - fail fast with clear message
            logger.error("Code analyzer LLM failed: %s", e, exc_info=True)
            _raise_llm_infrastructure_error(e, "Code analyzer")
            raise  # This line is never reached but satisfies static analyzers

    # LLM DECISION NODES

    def _decide_code_retrieval(self, state: TriageState) -> Dict:
        """LLM decides if we should retrieve code"""
        logger.info("LLM Decision: Should we retrieve code?")

        # Note: Repository validation happens in _run_error_parser and fails fast.
        # If we reach this point, the repository is valid.

        try:
            prompt = SHOULD_RETRIEVE_CODE_PROMPT.format(
                error_type=state.get("error_type", "Unknown"),
                language=state.get("language", "Unknown"),
                severity=state.get("severity", "Unknown"),
                needs_code=state.get("needs_code", True),
                file_hints=state.get("file_hints", []),
                search_strategy=state.get("search_strategy", "")
            )

            messages = [
                SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]

            response = self.routing_llm.invoke(messages, config={"callbacks": [self.token_callback]})

            json_text = _extract_json_text_from_response(response)
            decision = json.loads(json_text)

            reasoning = decision.get("reasoning", "")
            short_reason = (
                reasoning[:200] + "..." if isinstance(reasoning, str) and len(reasoning) > 200 else reasoning
            )
            logger.info(
                "Decision: %s - %s",
                decision.get("should_retrieve"),
                short_reason,
            )

            return {
                "should_retrieve_code": decision["should_retrieve"]
            }

        except Exception as e:
            logger.error("Routing LLM failed in retrieval decision, using fallback decision: %s", e, exc_info=True)
            # Default to retrieving code if decision fails
            return {
                "should_retrieve_code": True,
                "routing_fallback_used": True,
                "routing_fallback_reason": f"Retrieval decision LLM error: {str(e)}",
            }

    def _evaluate_retrieval(self, state: TriageState) -> Dict:
        """LLM evaluates retrieval success"""
        logger.info("LLM Evaluation: Was code retrieval successful?")

        try:
            snippets = state.get("code_snippets", []) or []
            code_content = state.get("code_content", "") or ""

            # Short-circuit: if we have successfully retrieved *all* hinted
            # files from the error parser, we consider retrieval good enough
            if self._have_all_hinted_files(state):
                logger.info(
                    "All hinted files were retrieved (%d snippets); skipping LLM retrieval evaluation and proceeding.",
                    len(snippets),
                )
                return {"retrieval_action": "proceed"}

            prompt = EVALUATE_RETRIEVAL_PROMPT.format(
                snippet_count=len(snippets),
                code_length=len(code_content),
                file_hints_attempted=state.get("file_hints", []),
                search_strategy_used=state.get("search_strategy", ""),
                repository=state.get("repository", ""),
                error_type=state.get("error_type", ""),
                severity=state.get("severity", "")
            )

            messages = [
                SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ]

            response = self.routing_llm.invoke(messages, config={"callbacks": [self.token_callback]})

            json_text = _extract_json_text_from_response(response)
            decision = json.loads(json_text)

            reasoning = decision.get("reasoning", "")
            short_reason = (
                reasoning[:200] + "..." if isinstance(reasoning, str) and len(reasoning) > 200 else reasoning
            )
            logger.info(
                "Retrieval evaluation: %s - %s",
                decision.get("action"),
                short_reason,
            )

            return {
                "retrieval_action": decision["action"]
            }

        except Exception as e:
            logger.error("Routing LLM failed in retrieval evaluation, using fallback decision: %s", e, exc_info=True)
            return {
                "retrieval_action": "proceed",
                "routing_fallback_used": True,
                "routing_fallback_reason": f"Retrieval evaluation LLM error: {str(e)}",
            }

    def _has_meaningful_code_context(self, state: TriageState) -> bool:
        """Check if state contains meaningful code context.

        Args:
            state: The triage state

        Returns:
            True if state has code context, False otherwise
        """
        code_content = state.get("code_content", "")
        code_snippets = state.get("code_snippets", []) or []
        return len(code_content.strip()) > MIN_CODE_CONTENT_LENGTH and len(code_snippets) > 0

    def _should_accept_high_confidence(self, state: TriageState) -> tuple[bool, str | None]:
        """Check if analysis should be accepted based on high confidence.

        Args:
            state: The triage state

        Returns:
            (should_accept, reason_if_not_accepted)
        """
        confidence = state.get("confidence", 0.0)

        if confidence < HIGH_CONFIDENCE_THRESHOLD:
            return False, None

        # High confidence - check if we have code context
        if self._has_meaningful_code_context(state):
            code_snippets = state.get("code_snippets", []) or []
            code_content = state.get("code_content", "")
            logger.info(
                "High confidence (%.2f >= %.2f) with code context (%d snippets, %d chars) - accepting analysis",
                confidence,
                HIGH_CONFIDENCE_THRESHOLD,
                len(code_snippets),
                len(code_content),
            )
            return True, None

        # High confidence but no code context - needs adjustment
        code_snippets = state.get("code_snippets", []) or []
        code_content = state.get("code_content", "")
        logger.warning(
            "High confidence (%.2f >= %.2f) but NO CODE CONTEXT retrieved (%d snippets, %d chars) - "
            "adjusting confidence and continuing evaluation",
            confidence,
            HIGH_CONFIDENCE_THRESHOLD,
            len(code_snippets),
            len(code_content),
        )
        return False, "high_confidence_without_code"

    def _adjust_confidence_for_missing_code(self, state: TriageState) -> float:
        """Adjust confidence when code context is missing.

        Code Analyzer self-adjusts confidence; this is a safety check.
        """
        confidence = state.get("confidence", 0.0)
        has_code = self._has_meaningful_code_context(state)
        is_generic = self._is_generic_response(state)

        if not has_code:
            if confidence > 0.1:
                logger.warning(
                    f"Code Analyzer returned confidence {confidence:.2f} without code - "
                    f"overriding to {GENERIC_RESPONSE_CONFIDENCE}"
                )
                return GENERIC_RESPONSE_CONFIDENCE
            return confidence

        if is_generic:
            logger.warning(f"Generic analysis detected - reducing confidence to {GENERIC_RESPONSE_CONFIDENCE}")
            return GENERIC_RESPONSE_CONFIDENCE

        logger.info(f"Trusting Code Analyzer confidence: {confidence:.2f}")
        return confidence

    def _mark_root_cause_as_generic(self, state: TriageState) -> None:
        """Add warning prefix to root cause indicating generic analysis.

        Args:
            state: The triage state (modified in place)
        """
        root_cause = state.get("root_cause", "")
        state["root_cause"] = (
            "⚠️ [GENERIC ANALYSIS - NO CODE RETRIEVED]\n\n" +
            root_cause +
            "\n\n" +
            "NOTE: This analysis is based only on error symptoms without actual code inspection. "
            "It represents common patterns for similar errors but lacks specific code evidence. "
            "Consider this highly speculative and use other observability data for validation."
        )

    def _evaluate_analysis(self, state: TriageState) -> Dict:
        """LLM evaluates analysis quality"""
        logger.info("LLM Evaluation: Is analysis good enough?")

        # Check if high confidence allows immediate acceptance
        should_accept, reason = self._should_accept_high_confidence(state)
        if should_accept:
            return {"analysis_action": "accept"}

        # If high confidence but no code, adjust confidence
        if reason == "high_confidence_without_code":
            adjusted_confidence = self._adjust_confidence_for_missing_code(state)

            # Mark as generic if applicable
            if adjusted_confidence == GENERIC_RESPONSE_CONFIDENCE:
                self._mark_root_cause_as_generic(state)

            # Update state with adjusted confidence for downstream processing
            state["confidence"] = adjusted_confidence
            # Continue to full LLM evaluation

        try:
            prompt = SHOULD_REFINE_ANALYSIS_PROMPT.format(
                root_cause=state.get("root_cause", ""),
                confidence=state.get("confidence", 0.0),
                severity=state.get("severity", ""),
                recommendations_count=len(state.get("recommendations", [])),
                analysis_needs_more_code=state.get("analysis_needs_more_code", False),
                analysis_additional_file_hints=state.get("analysis_additional_file_hints", []),
            )

            messages = [
                SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]

            response = self.routing_llm.invoke(messages, config={"callbacks": [self.token_callback]})

            json_text = _extract_json_text_from_response(response)
            decision = json.loads(json_text)

            reasoning = decision.get("reasoning", "")
            short_reason = (
                reasoning[:200] + "..." if isinstance(reasoning, str) and len(reasoning) > 200 else reasoning
            )
            logger.info(
                "Analysis evaluation: %s - %s",
                decision.get("action"),
                short_reason,
            )

            return {
                "analysis_action": decision["action"]
            }

        except Exception as e:
            logger.error("Routing LLM failed in analysis evaluation, using fallback decision: %s", e, exc_info=True)
            return {
                "analysis_action": "accept",
                "routing_fallback_used": True,
                "routing_fallback_reason": f"Analysis evaluation LLM error: {str(e)}",
            }

    # ROUTING FUNCTIONS

    def _route_after_retrieval_decision(
        self, state: TriageState
    ) -> Literal["retrieve", "skip"]:
        """Route based on retrieval decision"""
        if state.get("should_retrieve_code", True):
            return "retrieve"
        else:
            return "skip"

    def _route_after_retrieval_evaluation(
        self, state: TriageState
    ) -> Literal["proceed", "retry", "skip"]:
        """Route based on retrieval evaluation"""
        action = state.get("retrieval_action", "proceed")
        attempt_count = state.get("retrieval_attempt_count", 0)

        # Prevent infinite retries
        if attempt_count >= 3:
            logger.warning("Max retrieval attempts reached, proceeding anyway")
            return "skip"

        if action in ["retry_search", "retry_files"]:
            return "retry"
        elif action == "proceed_without_code":
            return "skip"
        else:
            return "proceed"

    def _route_after_analysis_evaluation(
        self, state: TriageState
    ) -> Literal["accept", "refine", "more_code"]:
        """Route based on analysis evaluation"""
        action = state.get("analysis_action", "accept")
        attempt_count = state.get("analysis_attempt_count", 0)

        # Prevent infinite retries
        if attempt_count >= 2:
            logger.warning("Max analysis attempts reached, accepting result")
            return "accept"

        if action == "refine_with_more_context":
            return "more_code"
        elif action == "refine_analysis":
            return "refine"
        else:
            return "accept"

    # REPORT GENERATION

    def _generate_report(self, state: TriageState) -> Dict:
        """Generate final triage report"""
        logger.info("Generating final report...")

        # Note: Repository validation check removed - we now fail fast in _run_error_parser()
        # If we reach this point, the repository is valid

        # Compact, human-readable summary of this triage run
        snippets = state.get("code_snippets") or []
        logger.info(
            "Triage summary: repo=%s, error_type=%s, severity=%s, code_snippets=%d, confidence=%.2f",
            state.get("repository", "<unknown>"),
            state.get("error_type"),
            state.get("severity"),
            len(snippets),
            state.get("confidence", 0.0),
        )

        # Get token usage from global tracker
        tracker = GlobalTokenTracker()
        all_counts = tracker.get_all_counts()
        grand_total = tracker.get_grand_total()

        # Log detailed token usage summary
        logger.info("[TOKEN_SUMMARY] ========== Token Usage Summary ==========")
        for agent_name, counts in sorted(all_counts.items()):
            logger.info(
                "[TOKEN_SUMMARY] %s: %d tokens (%d calls) - prompt=%d, completion=%d",
                agent_name,
                counts["total_tokens"],
                counts["call_count"],
                counts["prompt_tokens"],
                counts["completion_tokens"],
            )
        logger.info(
            "[TOKEN_SUMMARY] GRAND TOTAL: %d tokens across %d LLM calls (prompt=%d, completion=%d)",
            grand_total["total_tokens"],
            grand_total["call_count"],
            grand_total["prompt_tokens"],
            grand_total["completion_tokens"],
        )
        logger.info("[TOKEN_SUMMARY] ==========================================")

        # Check if routing fallback was used and add warning
        warnings = []
        if state.get("routing_fallback_used"):
            fallback_reason = state.get("routing_fallback_reason", "Unknown reason")
            warning_msg = f"Intelligent routing unavailable: {fallback_reason}. Used default workflow decisions."
            warnings.append(warning_msg)
            logger.warning("Routing fallback was used: %s", fallback_reason)

        # Check if any file retrievals failed and add warning
        retrieval_failures = state.get("retrieval_failures", [])
        if retrieval_failures:
            failed_count = len(retrieval_failures)
            # Format failures for display (limit to first 5 to avoid overwhelming the user)
            failures_display = retrieval_failures[:5]
            failures_str = ", ".join([f"{file} ({reason})" for file, reason in failures_display])
            if failed_count > 5:
                failures_str += f", and {failed_count - 5} more"

            warning_msg = f"Failed to retrieve {failed_count} file(s): {failures_str}"
            warnings.append(warning_msg)
            logger.warning("Retrieval failures included in report: %d files", failed_count)

        # Check if analysis was done without code context
        has_code = self._has_meaningful_code_context(state)
        confidence = state.get("confidence", 0.0)

        if not has_code and confidence > 0.5:
            warning_msg = (
                f"Analysis performed without code context (confidence: {confidence:.2f}). "
                "Root cause diagnosis is based only on error messages and stack traces, "
                "not actual code inspection. Consider this analysis as preliminary."
            )
            warnings.append(warning_msg)
            logger.warning("Analysis without code context included in report (confidence: %.2f)", confidence)

        return {
            "status": "success",
            "error_summary": {
                "error_type": state.get("error_type"),
                "language": state.get("language"),
                "severity": state.get("severity"),
                "file_hints": state.get("file_hints"),
            },
            "warnings": warnings if warnings else None,
        }

    # HELPER METHODS

    def _is_generic_response(self, state: TriageState) -> bool:
        """Detect if analysis is generic using Code Analyzer's self-assessment."""
        analysis_is_specific = state.get("analysis_is_specific", False)
        code_references_count = state.get("code_references_count", 0)
        root_cause = state.get("root_cause", "")

        if not root_cause or len(root_cause.strip()) < MIN_ROOT_CAUSE_LENGTH:
            logger.warning("Root cause too short - treating as generic")
            return True

        if not analysis_is_specific:
            logger.warning("Code Analyzer marked analysis as NOT specific")
            return True

        has_code = self._has_meaningful_code_context(state)
        if has_code and code_references_count == 0:
            logger.warning("Code available but no file:line references - treating as generic")
            return True

        logger.info(f"Analysis is specific (code_references_count={code_references_count})")
        return False

    def _have_all_hinted_files(self, state: TriageState) -> bool:
        """Return True if all file_hints have been retrieved as code_snippets.

        This is used to short-circuit retrieval evaluation in simple cases
        where we clearly have the key files (e.g., main file + imported
        module for an ImportError), regardless of total character count.
        """

        hints = [h for h in (state.get("file_hints") or []) if h]
        if not hints:
            return False

        snippets = state.get("code_snippets") or []
        retrieved_paths = {
            s.get("file_path")
            for s in snippets
            if isinstance(s, dict) and s.get("file_path")
        }

        return set(hints).issubset(retrieved_paths)

    def _parse_error(self, error: str) -> tuple[str, str]:
        """
        Parse combined error into error_message and stack_trace

        Args:
            error: Complete error output

        Returns:
            Tuple of (error_message, stack_trace)
        """
        lines = error.strip().split('\n')

        # Try to find the actual error message (usually the last line or contains "Error:")
        error_message = ""
        stack_trace = ""

        # Look for common error patterns
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in ['Error:', 'Exception:', 'Traceback']):
                # Everything from this point is part of the error
                if 'Traceback' in line:
                    # This is the start of a stack trace
                    stack_trace = '\n'.join(lines[i:])
                    # Error message is usually the last line
                    if lines:
                        error_message = lines[-1]
                else:
                    # This line contains the error
                    error_message = line
                    # Rest is stack trace
                    if i > 0:
                        stack_trace = '\n'.join(lines[:i])
                break

        # If no pattern found, treat first line as error message, rest as stack trace
        if not error_message:
            error_message = lines[0] if lines else error
            stack_trace = '\n'.join(lines[1:]) if len(lines) > 1 else ""

        return error_message, stack_trace

    async def _run_triage_workflow_async(self, error: str, repository: str) -> Dict[str, Any]:
        """Async triage workflow that returns a structured report.

        This is the preferred entrypoint for async transports like the A2A
        AgentExecutor. It invokes the LangGraph workflow via its async API so
        that async subgraphs (e.g., code retrieval) can run without creating
        nested event loops.
        """
        logger.info("Starting intelligent triage for %s", repository)

        # Parse error into message and stack trace
        error_message, stack_trace = self._parse_error(error)

        # Reset global token tracker for this workflow run
        GlobalTokenTracker().reset()

        # Create initial state
        initial_state: TriageState = {
            "error_message": error_message,
            "stack_trace": stack_trace,
            "repository": repository,
            "error_type": None,
            "language": None,
            "file_hints": None,
            "line_hints": None,
            "search_strategy": None,
            "needs_code": None,
            "severity": None,
            "code_snippets": None,
            "code_content": None,
            "retrieval_attempt_count": 0,
            "root_cause": None,
            "affected_code": None,
            "recommendations": None,
            "confidence": None,
            "analysis_attempt_count": 0,
            "analysis_needs_more_code": None,
            "analysis_additional_file_hints": None,
            "should_retrieve_code": None,
            "retrieval_action": None,
            "analysis_action": None,
            "routing_fallback_used": None,
            "routing_fallback_reason": None,
            "status": "processing",
            "error_summary": None,
            "warnings": None,
        }

        # Run workflow with LLM-based routing using the async API so that
        # async nodes (like code retrieval) are awaited correctly.
        final_state = await self.workflow.ainvoke(initial_state)

        # Get token usage for the report
        tracker = GlobalTokenTracker()
        all_counts = tracker.get_all_counts()
        grand_total = tracker.get_grand_total()

        # Build structured report
        report: Dict[str, Any] = {
            "status": final_state.get("status", "success"),
            "error_summary": final_state.get("error_summary"),
            "root_cause": final_state.get("root_cause"),
            "responsible_code": (
                final_state.get("code_snippets", [{}])[0]
                if final_state.get("code_snippets")
                else None
            ),
            "suggested_fix": final_state.get("recommendations", []),
            "confidence": final_state.get("confidence", 0.0),
            "error_message": error_message,
            "workflow_stats": {
                "retrieval_attempts": final_state.get("retrieval_attempt_count", 0),
                "analysis_attempts": final_state.get("analysis_attempt_count", 0),
            },
            "token_usage": {
                "by_agent": all_counts,
                "total": grand_total,
            },
        }

        # Add warnings if any routing fallbacks were used
        if final_state.get("warnings"):
            report["warnings"] = final_state.get("warnings")

        logger.info("Intelligent triage completed successfully")
        return report

    def _run_triage_workflow(self, error: str, repository: str) -> Dict[str, Any]:
        """Synchronous wrapper for the triage workflow.

        This is kept for backwards compatibility with the legacy HTTP server
        path, which expects a blocking call. It simply runs the async
        implementation in a fresh event loop.
        """

        return asyncio.run(self._run_triage_workflow_async(error=error, repository=repository))

    def triage(self, error: str, repository: str) -> Dict:
        """Execute triage workflow and wrap result in legacy content format.

        This preserves the existing HTTP / JSON-RPC response shape while
        allowing the core workflow to be reused by the upcoming A2A
        AgentExecutor, which will consume the raw report dict instead.
        """
        try:
            report = self._run_triage_workflow(error=error, repository=repository)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(report),
                    }
                ]
            }
        except Exception as e:
            logger.error("Error during triage: %s", e, exc_info=True)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "error",
                                "error_message": str(e),
                                "error_type": type(e).__name__,
                            }
                        ),
                    }
                ]
            }


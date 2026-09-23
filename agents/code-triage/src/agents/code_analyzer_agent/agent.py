"""LangChain code analyzer agent and structured output model."""

from __future__ import annotations

from typing import List, Literal

from langchain.agents import create_agent
from langchain.messages import HumanMessage
from pydantic import BaseModel

from .prompts import CODE_ANALYZER_SYSTEM_PROMPT, CODE_ANALYZER_USER_PROMPT_TEMPLATE
from src.llm_client import get_llm, get_prompt_caching_middleware
from src.agents.middlewares import TokenCountingCallback, CacheMonitoringMiddleware
import logging

logger = logging.getLogger(__name__)


class CodeAnalysisResult(BaseModel):
    """Structured output for the code analyzer agent."""

    root_cause: str
    affected_code: str
    recommendations: List[str]
    confidence: float
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    # Analyzer's own judgment about whether the current code context is
    # sufficient for a high-quality diagnosis.
    needs_more_code: bool = False
    # Optional additional file paths or hints it would like retrieved.
    additional_file_hints: List[str] = []

    # LLM self-assessment fields
    analysis_is_specific: bool = True  # True if analysis references specific code
    code_references_count: int = 0  # Count of file:line references (e.g., "payment.py:42")


# Token counting callback for this agent
_code_analyzer_token_callback = TokenCountingCallback(name="code_analyzer")

# Build middleware list with prompt caching support and cache monitoring
_middlewares = []
_caching_middleware = get_prompt_caching_middleware()
if _caching_middleware:
    _middlewares.append(_caching_middleware)
    logger.info("code_analyzer_agent: Prompt caching middleware enabled")

# Add cache monitoring middleware to track cache hits/misses
_cache_monitor = CacheMonitoringMiddleware(agent_name="code_analyzer")
_middlewares.append(_cache_monitor)

code_analyzer_agent = create_agent(
    model=get_llm(temperature=0.1, max_tokens=2000),
    tools=[],
    system_prompt=CODE_ANALYZER_SYSTEM_PROMPT,
    response_format=CodeAnalysisResult,
    name="code_analyzer_agent",
    middleware=_middlewares if _middlewares else None,
)


def analyze_with_agent(error_message: str, stack_trace: str, code_content: str) -> CodeAnalysisResult:
    """Run the code analyzer agent and return a CodeAnalysisResult.

    Mirrors the pattern used for the other subagents: invoke the agent to
    get its state dict, then extract and validate the structured response.
    """

    user_prompt = CODE_ANALYZER_USER_PROMPT_TEMPLATE.format(
        error_message=error_message,
        stack_trace=stack_trace,
        code_content=code_content,
    )

    agent_state = code_analyzer_agent.invoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config={"callbacks": [_code_analyzer_token_callback]}
    )

    if isinstance(agent_state, CodeAnalysisResult):
        return agent_state

    candidate = None
    if isinstance(agent_state, dict):
        if "structured_response" in agent_state:
            candidate = agent_state["structured_response"]
        else:
            candidate = agent_state
    else:
        candidate = agent_state

    if isinstance(candidate, CodeAnalysisResult):
        return candidate
    if isinstance(candidate, dict):
        return CodeAnalysisResult.model_validate(candidate)

    # Fallback: construct a very low-confidence analysis
    return CodeAnalysisResult(
        root_cause=str(getattr(candidate, "root_cause", "Unknown root cause")),
        affected_code=str(getattr(candidate, "affected_code", "")),
        recommendations=list(getattr(candidate, "recommendations", [])) or [
            "Review the error and surrounding code context.",
        ],
        confidence=float(getattr(candidate, "confidence", 0.2)),
        severity=str(getattr(candidate, "severity", "medium")),
        needs_more_code=bool(getattr(candidate, "needs_more_code", False)),
        additional_file_hints=list(getattr(candidate, "additional_file_hints", [])) or [],
        analysis_is_specific=bool(getattr(candidate, "analysis_is_specific", False)),
        code_references_count=int(getattr(candidate, "code_references_count", 0)),
    )

